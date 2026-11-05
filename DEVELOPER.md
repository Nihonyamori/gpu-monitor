# GPU Monitor — 開発者向けドキュメント

NVIDIA GPU の負荷（GPU使用率・メモリ使用率・消費電力・温度・メモリ絶対値）をリアルタイムに表示する小型 tkinter GUI プログラムの実装説明と、今後修正するための情報。

- ソース: `gpu_monitor.py`（全ロジックを1ファイルに集約）
- 依存: Python 3 標準ライブラリ（`tkinter` / `ctypes` / `subprocess` / `socket` / `fcntl` / `pwd` / `argparse` / `json` など）+ NVIDIA ドライバ（`libnvidia-ml.so.1` か `nvidia-smi`）
- 追加のパッケージは不要。

---

## 1. ファイル構成

```
programs/gpu_monitor/
├── gpu_monitor.py     # 本体（全ロジックを1ファイルに集約）
├── install.sh         # アプリメニュー・自動起動への登録 / 削除
├── icon.svg           # アイコン原本（メニュー用）
├── icon.png           # icon.svg から作った 256px PNG（ウィンドウ・Dock 用）
├── README.md          # 概要（英語・日本語）
├── USER.md            # ユーザ向け説明（英語）
├── USER_J.md          # ユーザ向け説明（日本語）
├── DEVELOPER.md       # このファイル（開発者向け）
├── gpu_monitor.png    # README 用スクリーンショット
├── LICENSE            # MIT License
├── pyproject.toml     # pipx / pip 用パッケージ定義（gpu-monitor コマンド）
├── scripts/
│   └── release_notes.py   # CHANGELOG の節を取り出す（release.yml が使う）
├── docs/              # README の画像（compact.png / processes.png）
├── CHANGELOG.md       # 変更履歴（__version__ と揃える）
├── .gitignore         # __pycache__ を除外
├── tests/
│   └── test_gpu_monitor.py   # unittest（GPU 不要）
└── .github/workflows/
    ├── test.yml       # push / PR でテスト + pipx install の確認
    └── release.yml    # v* タグの push でテスト → GitHub リリース作成

実行時に自動生成:
~/.config/gpu_monitor.json            # 設定（常に手前・グラフ・コンパクト表示・不透明度・ウィンドウ位置）
$XDG_RUNTIME_DIR/gpu-monitor-<uid>-<DISPLAY>.lock / .sock   # 二重起動防止

install.sh が生成:
~/.local/share/applications/gpu-monitor.desktop              # アプリメニュー
~/.local/share/icons/hicolor/scalable/apps/gpu-monitor.svg   # アイコン
~/.local/share/icons/hicolor/256x256/apps/gpu-monitor.png    # アイコン（PNG）
~/.config/autostart/gpu-monitor.desktop                      # 自動起動（--autostart 時）
```

---

## 2. モジュール構造（gpu_monitor.py）

### 2-1. モジュール上定数（docstring と import の直後）

| 定数 | 意味 | 既定値 |
|---|---|---|
| `__version__` | バージョン（`--version`・メニュー最下段・CHANGELOG.md・pyproject.toml） | `1.1.0` |
| `REFRESH_MS` | 更新間隔の既定値 (ms) | `500` |
| `UPDATE_INTERVALS_MS` | 更新間隔の選択肢 (ms) | `(500, 1000, 2000, 5000)` |
| `QUERY_TIMEOUT_S` | nvidia-smi のタイムアウト (s) | `2` |
| `CONFIG_FILE` | 設定ファイルパス | `~/.config/gpu_monitor.json` |
| `NVML_LIB` | NVML の共有ライブラリ名 | `libnvidia-ml.so.1` |
| `ICON_FILE` | ウィンドウアイコン | `gpu_monitor.py` と同じフォルダの `icon.png` |
| `WM_CLASS` | X11 の WM_CLASS（install.sh の `StartupWMClass` と対応） | `gpu-monitor` |
| `BAR_W` / `BAR_H` | 使用率バーの幅 / 高 (px、Medium 時。文字サイズの倍率を掛ける) | `160` / `12` |
| `TEMP_WARN` / `TEMP_BAD` | 温度を黄 / 赤にする温度 (°C) | `80` / `90` |
| `GRAPH_H` / `LEGEND_H` | 履歴グラフの高さ / 上部の凡例帯の高さ (px) | `44` / `12` |
| `GRAPH_SECONDS` | グラフの期間 (秒)。点数は更新間隔から決まる | `60` |
| `TEXT_SIZES` | 文字サイズの名前 → 倍率 | `small 0.85` / `medium 1.0` / `large 1.3` |
| `PROC_LIMIT` | プロセス一覧の最大行数 | `15` |
| `GRAPH_MENU_LABEL` | グラフのメニュー項目名（有効・無効の切替に使う） | `Show history graph (60 s)` |
| `OPACITY_LEVELS` | 不透明度の選択肢 (%) | `(100, 90, 80, 70, 60)` |
| `BG` / `CARD_BG` | ウィンドウ背景 / カード背景 | `#1e1e2e` / `#2a2a3c` |
| `FG` / `DIM` | 前景テキスト / 薄めテキスト | `#e6e6f0` / `#9a9ab0` |
| `GOOD` / `WARN` / `BAD` | 低負荷 / 中負荷 / 高負荷の色 | 緑 / 黄 / 赤 |
| `BAR_BG` | バー未使用部・グラフ・ツールチップの背景 | `#15151f` |
| `LINE_UTIL` / `LINE_TEMP` | グラフの線（GPU 使用率 / 温度） | 青 `#60a5fa` / オレンジ `#fb923c` |

> テーマ変更はこの定数ブロックの HEX 値を差し替えるだけ。

### 2-2. 関数・クラス一覧

```
load_config() -> dict
    ~/.config/gpu_monitor.json を JSON で読込。
    存在しない/壊れている/dict でない場合は空辞書 {} を返す（起動は止めない）。

save_config(cfg: dict)
    同上ファイルへ JSON 書き込み。失敗しても例外を投げない（静かに無視）。
    key: "always_on_top" (bool), "show_graph" (bool), "compact" (bool),
         "opacity" (int, OPACITY_LEVELS のどれか), "text_size" (TEXT_SIZES の名前),
         "interval_ms" (int, UPDATE_INTERVALS_MS のどれか), "x" / "y" (int, ウィンドウ位置)

update_config(**values)
    load_config() → 値を書き足し → save_config()。設定の保存は全部これを使う。

color_for_pct(pct) -> str
    使用率から色を返す。
      pct >= 90  -> BAD  (赤)
      pct >= 70  -> WARN (黄)
      それ以下   -> GOOD (緑)

color_for_temp(temp) -> str
    温度の文字色。TEMP_BAD 以上 BAD、TEMP_WARN 以上 WARN、それ以下 DIM。

fmt_mib(mib) -> str          1 GiB 以上は "14.6 GiB"、未満は "512 MiB"
fmt_mem_pair(used, total)    "6.5/8.0 GiB"（詳細行用、常に GiB）

choose_position(saved, sw, sh, w) -> (x, y)
    最初にウィンドウを置く位置。saved (設定の x, y) が int で、50px 以上
    画面内に残るならそれ、そうでなければ右上から 20px 内側。

make_gpu(index, name, temp, util, mem_total, mem_used, power, power_limit) -> dict
    両方のデータソースが返す GPU 1 枚分の dict を作る（% はここで計算）。
    dict のキー（GUI側がこれを読む）:
      index        int    GPU 番号（nvidia-smi の index と同じ）
      name         str    GPU名 (例 "NVIDIA GeForce RTX 3090")
      temp         float  温度 (°C)
      util         float  GPU 使用率 %
      mem_total    float  メモリ総量 (MiB)
      mem_used     float  メモリ使用量 (MiB)
      mem_pct      float  メモリ使用率 % (mem_used/mem_total*100)
      power        float  消費電力 (W)
      power_limit  float  電力上限 (W)
      power_pct    float  消費電力率 % (power/power_limit*100)
    GPU が返さない値（[N/A]、NVML の NOT_SUPPORTED）は 0。

_run_smi(*args) -> str
    nvidia-smi を QUERY_TIMEOUT_S 付きで実行して stdout を返す。

query_gpus() -> list[dict]
    nvidia-smi で全GPUの情報を取得する（SmiSource の中身）。
    裏のコマンド:
      nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,\
                            memory.total,memory.used,power.draw,power.limit \
                  --format=csv,noheader,nounits
    QUERY_TIMEOUT_S 秒で応答がなければ subprocess.TimeoutExpired。
    例外はここでは捕捉せず、refresh() 側で処理する。

class SmiSource          name = "nvidia-smi"
    .query()             query_gpus() を呼ぶだけ
    .processes(index)    nvidia-smi --query-compute-apps=pid,used_memory -i index
                         （CSV で取れるのは compute プロセスだけ）
    .close()             何もしない

class NvmlSource         name = "NVML"
    ctypes で libnvidia-ml.so.1 を直接呼ぶ。プロセス起動がなく 1 回約 2ms。
    __init__  ライブラリ読込 + nvmlInit_v2。失敗時は OSError / NvmlError。
    .query()  nvmlDeviceGetCount_v2 → GPU ごとに Name / UtilizationRates /
              Temperature / PowerUsage / PowerManagementLimit / MemoryInfo。
              メモリは v2 API（予約領域を除く使用量で nvidia-smi と一致）、
              v2 が無い古いドライバでは v1。
              NOT_SUPPORTED は 0 扱い、それ以外のエラーは NvmlError。
    .processes(index)
              nvmlDeviceGet{Compute,Graphics}RunningProcesses_v3 を呼び、
              pid ごとにまとめる（kind "C" / "G" / "C+G"、mem は MiB か None）。
              1 回目で件数を聞き、余裕 (+8) を持った配列で 2 回目を呼ぶ。
              _v3 が無い古いドライバでは None。
    .close()  nvmlShutdown

open_source(use_smi=False)
    NvmlSource を試し、失敗したら（または use_smi なら）SmiSource を返す。
    NVML を使えなかった理由は stderr に 1 行出す。

short_error(e) -> str
    データソースの例外を状態行用の短い 1 行にする。
      NvmlError           -> "NVML: <NVML のエラー文>"  (例 "NVML: GPU is lost")
      FileNotFoundError   -> "nvidia-smi not found"
      TimeoutExpired      -> "nvidia-smi timed out (2s)"
      CalledProcessError  -> "nvidia-smi failed (exit N)"
      その他              -> 例外クラス名
    str(CalledProcessError) は引数一覧を含み約 200 文字あり、そのまま出すと
    ウィンドウ幅が広がって戻らなくなる（_max_req）ため、必ずこれを通す。

describe_pid(pid) -> (user, command)
    /proc/<pid> の所有者とコマンドライン。見えなければ ("?", "?")。

format_processes(procs, limit=PROC_LIMIT) -> str
    processes() の結果を固定幅の表（PID / USER / MEM / TYPE / COMMAND）に。
    メモリの大きい順、不明 (None) は最後。コマンドは 40 文字で切る。

class SingleInstance(run_dir=None)
    二重起動防止。$XDG_RUNTIME_DIR/gpu-monitor-<uid>-<DISPLAY>.lock を flock、
    同名の .sock で待ち受ける。
    .acquire()   1 つ目なら True。2 つ目は .sock に接続して 1 つ目を前に出させ False
    .attach(root, on_request)   接続が来たら on_request()（createfilehandler）
    .close()     ソケットを閉じて削除、ロックを解放

class Style(root, text_size="medium")
    文字サイズごとのフォントとピクセル寸法。フォントは Tk の名前付きフォント
    （.normal / .bold / .title / .small / .mono）なので、set_size() で使っている
    ウィジェットがすべて一度に変わる。
    .set_size(name)   TEXT_SIZES の名前（不明なら medium）を適用
    .px(n)            ピクセル寸法に倍率を掛ける
    .pct_w            "100%" を bold で実測した幅 + 余白（バー右の % 欄）
    バー・グラフのピクセル寸法は作成時に読むので、サイズ変更後はカードを作り直す。

class BarWidget(parent, row, label_text, style)
    1本の「横バー + パーセント表示」。
    .label   tk.Label ("GPU"/"MEM"/"PWR")
    .canvas  tk.Canvas (幅 bar_w + style.pct_w)。0〜bar_w にバー、その右に
             % を右寄せで描く。% をバーの外に置くので、90% 以上（赤）でも
             塗りと重ならず読める
    .rect / .txt  canvas 内の図形ID
    .set(pct)  幅・色・数値を 1 度に更新 (0〜100 にクランプ)

class History(points)
    GPU 1 枚の直近 GRAPH_SECONDS 秒の使用率と温度（deque、maxlen = points）。
    App が (index, name) ごとに持つので、カードを作り直しても・グラフ非表示でも残る。
    .add(util, temp) / .resize(points)（新しい値を残して点数を変える）/ .points

class HistoryGraph(parent, row, style)
    History の折れ線（どちらも 0〜100）。上 LEGEND_H px が凡例、その下が描画領域。
    最新が右端。.show(history) で描く History を渡す。.set_visible(on)

class GpuCard(parent, idx, name, style, show_graph=True)
    1GPU分のカード(Frame)。タイトルは "GPU <index>  <name>"。
    .index / .name   GPU 番号と名前（プロセス一覧の取得・見出しに使う）
    .util_bar  BarWidget (GPU使用率)
    .mem_bar   BarWidget (メモリ使用率)
    .pwr_bar   BarWidget (消費電力率)
    .mem_lbl / .temp_lbl / .pwr_lbl
               詳細行。温度だけ色を変えるため 3 つのラベルに分けている
    .graph     HistoryGraph
    .update(g, history=None)  make_gpu() の dict 1件とグラフ用の History を反映
    .set_graph_visible(on)

pointer_inside(widget) -> bool
    マウスポインタが widget の中にあるか（プロセス一覧を隠すかの判定）。

class CompactRow(parent, idx, name, style)
    コンパクト表示の 1 行 "GPU 0  G 17%  M 9%  P 8%  48°C"。GpuCard と同じ
    インタフェース（index / name / frame / update(g, history) / set_graph_visible。後の 2 つのグラフ部分は何もしない）
    なので、App は表示モードを気にせず扱える。

class Tooltip(root, style)
    枠なし (overrideredirect) の Toplevel。widget の左に出し、入らなければ右。
    .show(owner, widget, text) / .hide() / .owner（表示中のカード）

class App(source, always_on_top=None, reset_position=False)
    メインウィンドウ。
    __init__  always_on_top が None なら設定ファイルの値を採用。
              reset_position でなければ保存位置 (x, y) を覚えておく。
              tk.Tk(className=WM_CLASS) で作成し、icon.png を iconphoto に設定
              （無ければ既定のアイコンのまま）。
              ヘッダー・トグルボタン・カード枠・状態行を作成し、refresh() を開始。
    .source       データソース（NvmlSource / SmiSource）
    .top_btn      「常に手前」トグルボタン
    .style        Style（フォントと寸法）
    .topmost_var / .graph_var / .compact_var / .opacity_var / .text_size_var / .interval_var
                  メニューのチェック・選択と同期する変数
    .menu         メニュー（常に手前 / コンパクト表示 / グラフ / 文字サイズ / 更新間隔 /
                  不透明度 / 右上へ移動 / 終了 / バージョン）。右クリックと .menu_btn（⋮）で開く
    .history      {(index, name): History}。消えた GPU の分は _rebuild_cards で捨てる
    .graph_points GRAPH_SECONDS 秒分の点数（更新間隔から計算）
    .tooltip      Tooltip（プロセス一覧）
    .cards        GpuCard のリスト。._card_keys = [(index, name)]
    .set_topmost(on)    属性・ボタンの色・メニューのチェックを揃える
    ._save_topmost(on)  ボタン・メニューから。set_topmost + 保存
    ._toggle_graph()    全カードのグラフ表示を切替 + 保存 + _fit()
    ._toggle_compact()  保存 → _apply_compact_layout() → _relayout()
    ._set_text_size()   style.set_size() → 保存 → _relayout()
    ._set_interval()    保存 → 全 History を resize → refresh()（新しい間隔で予約し直す）
    ._relayout()        カードを作り直して直近の値（_last_gpus）を表示 → 幅が縮めるよう
                        _max_req = 0 → _fit()
    ._update_cards(gpus)  各カードに値と History を渡す
    ._apply_compact_layout()  コンパクト時はメモリ合計の行を隠し、グラフの
                        メニュー項目を無効にする
    ._set_opacity()     wm_attributes("-alpha") + 保存
    .bring_to_front()   2 つ目の起動時に呼ばれる。deiconify / lift と、
                        一時的な topmost で確実に前面へ
    ._place_once()      初回の refresh で 1 回だけ choose_position() の位置に
                        配置（成功・エラーどちらでも）。サイズは内容に合わせる
    ._move_top_right()  メニューから。今すぐ右上へ
    ._on_card_enter / ._on_card_leave / ._show_processes
                        カードの <Enter> でプロセス一覧を表示。<Leave> は子
                        ウィジェットに移っただけでも来るので、80ms 後に
                        pointer_inside() で確かめてから隠す
    ._rebuild_cards(gpus)  カードを全部作り直す
    ._fit()             更新毎にウィンドウサイズを内容に追随。
                        サイズだけ指定し、位置はウィンドウマネージャに任せる
    .close()            位置を保存 → 予約中の refresh を取り消し → ツールチップを
                        閉じる → source.close() → root.destroy()。閉じるボタン・
                        メニュー・SIGINT / SIGTERM から呼ばれる（2 回目以降は無視）
    .refresh()          直接呼ばれた時は予約中のタイマーを取り消す（ループは常に 1 本）。
                        500ms ごとに source.query() → GPU 構成が変わっていれば
                        _rebuild_cards() → 全カード更新 → 表示中のプロセス一覧も更新 →
                        self.root.after(REFRESH_MS, ...) で再帰スケジュール

main()
    argparse で CLI をパース（-A / --no-always-on-top / -R / --nvidia-smi /
    --new-instance / --version）。--new-instance でなければ SingleInstance.acquire() し、
    2 つ目ならそのまま終了。open_source() でソースを選び App を作成、
    SingleInstance を attach、SIGINT / SIGTERM で close() を予約するハンドラを
    登録してから mainloop()。終了時に SingleInstance.close()。
```

### 2-3. 起動フロー

```
main()
  ├─> SingleInstance.acquire()   2 つ目なら 1 つ目を前に出して終了
  ├─> open_source()          NVML → 失敗なら nvidia-smi
  └─> App(source, ...).root.mainloop()
         ├─> refresh()            (source.query() #1)
         │      ├─ エラーなら状態行に short_error() を出し、_place_once() して次回へ
         │      ├─ GPU 構成 (index, name) が変わっていれば _rebuild_cards()
         │      ├─ card.update(g) を各GPUへ（グラフにも 1 点追加）
         │      ├─ プロセス一覧の表示中なら取り直す
         │      ├─ _place_once()（1 回だけ）→ _fit()
         │      └─ root.after(REFRESH_MS, refresh)   ← 再ポーリング
         └─> mainloop             (イベントループ)
               └─ ✕ / Ctrl+C / kill → close()  位置を保存して終了
```

### 2-4. 状態保持

- 保存されるのは「常に手前」・グラフ表示・コンパクト表示・不透明度・文字サイズ・更新間隔・ウィンドウ位置。
  → `~/.config/gpu_monitor.json`（例: `{"always_on_top": true, "show_graph": true, "text_size": "medium", "interval_ms": 500, "x": 2932, "y": 20}`）
  - `always_on_top` はボタン・メニューで切り替えたときに保存。`-A` / `--no-always-on-top` は保存しない。
  - `show_graph` / `compact` / `opacity` / `text_size` / `interval_ms` はメニューで切り替えたときに保存。
    既定は true / false / 100 / medium / 500。選択肢に無い値は既定値として扱う。
  - `x` / `y` は終了時（`close()`）に `wm geometry` の値から保存。同じ値を
    `geometry()` に渡すと同じ場所に開くので、起動を繰り返しても位置はずれない。
- ウィンドウサイズ・色テーマ等は**未保存**（毎回初期値）。
  必要なら `load_config()` / `save_config(cfg)` に key を追加するだけ。
- **ウィンドウ幅調整**: `_place_once()` で初期配置、`_fit()` で内容幅に追随（余白無し）。
  幅の安定化は `_max_req` を保持し、`max(_max_req, 180)` → 必要以上の縮小を防止。

---

## 3. 修正のよくあるポイント

| 目的 | 見る箇所 |
|---|---|
| 更新間隔の既定値・選択肢 | `REFRESH_MS` / `UPDATE_INTERVALS_MS` |
| 文字サイズの選択肢・倍率 | `TEXT_SIZES`、フォントの基準サイズは `Style.set_size()` |
| nvidia-smi のタイムアウト | `QUERY_TIMEOUT_S` |
| バー・% 表示の幅 | `BAR_W`、% 欄は `Style.pct_w` |
| エラーメッセージ | `short_error(e)` |
| 色テーマ変更 | `BG` / `CARD_BG` / `GOOD` / `WARN` / `BAD` 等のHEX |
| 黄/赤の閾値変更 | `color_for_pct(pct)`（`>=90` / `>=70` の数字）、温度は `TEMP_WARN` / `TEMP_BAD` |
| メモリの表示形式 | `fmt_mib()` / `fmt_mem_pair()` |
| グラフの期間・高さ・線 | `GRAPH_SECONDS` / `GRAPH_H` / `HistoryGraph.draw()` |
| プロセス一覧の列・行数 | `format_processes()` / `PROC_LIMIT`、取得は各ソースの `processes()` |
| メニューの項目 | `App.__init__` の `self.menu`（「⋮」ボタンは `self.menu_btn`） |
| コンパクト表示の内容 | `CompactRow` |
| 不透明度の選択肢 | `OPACITY_LEVELS` |
| バージョンを上げる | `__version__` と `CHANGELOG.md`（下記「リリース手順」）。pyproject.toml は `__version__` を読む |
| パッケージ定義 | `pyproject.toml`（コマンド名 `gpu-monitor` → `gpu_monitor:main`） |
| 二重起動防止 | `SingleInstance` / `--new-instance` |
| 表示項目追加 | `make_gpu()` にキー追加 → 両ソース（`NvmlSource.query()` / `query_gpus()`）で値を取得 → `GpuCard.update(g)` で描画 |
| 消費電力の表示/閾値 | `NvmlSource.query()` の PowerUsage / PowerManagementLimit、`query_gpus()` の `power.draw/power.limit`、`GpuCard` の `pwr_bar` |
| データソースの選択 | `open_source()` / `--nvidia-smi` |
| 複数/動的 GPU | `App.refresh()` の構成比較と `App._rebuild_cards()` |
| 常に手前の初期値 | `load_config()` の既定 or `~/.config/gpu_monitor.json` |
| ウィンドウ幅・配置 | `App._place_once()` / `App._fit()` / `root.geometry` |
| 終了時の処理 | `App.close()` |
| 新規状態の永続 | `load_config`/`save_config` に key 追加 + 使用箇所 |
| メニュー項目の内容 | `install.sh` の `[Desktop Entry]` |
| アイコン | `icon.svg` を編集 → `icon.png` を作り直す（下記） |

### 設計上の注意

- **tkinter のシングルスレッド前提**：データ取得は同期呼び出し。NVML なら 1 回約 2ms、
  nvidia-smi なら 1 回 30〜40ms（GTX 1070 + RTX 3090 の環境）。
  nvidia-smi が固まった場合に備えて `QUERY_TIMEOUT_S` で打ち切る（その間は GUI が止まる）。
  NVML の呼び出しには timeout を付けられないが、ドライバ異常時は通常エラー
  （`GPU is lost` 等）が返るだけで止まらない。
  長い処理（外部API等）を入れる場合は `threading` で取り、結果は `root.after` でUIスレッドへ戻すパターンが安全。
- **NVML を ctypes で呼ぶ理由**：pip パッケージ（pynvml）を使わず標準ライブラリだけで済ませるため。
  関数の引数・構造体は NVML の C ヘッダ（`nvml.h`）に合わせてある。関数を追加する時は
  `restype`（既定は int）と引数の型に注意。
- **ドライバが無い環境**：NVML の読込に失敗して nvidia-smi に切り替わり、状態行に
  `Error: nvidia-smi not found` を表示する。
- **GPU の増減**：毎回 `[(index, name)]` を前回と比べ、変わっていればカードを全部作り直す
  （消えた GPU のグラフ履歴は捨てる）。0 枚ならカードは無く「0 GPUs」。幅は `_max_req` のため縮まない。
- **プロセス一覧**：取得はマウスが乗っている間だけ（毎 refresh）。NVML は compute と graphics の
  両方、nvidia-smi は compute だけ。ユーザ名とコマンドは `/proc` から読むので、別コンテナ
  （PID 名前空間）のプロセスは `?` になる。
- **二重起動防止**：ロックは `fcntl.flock` なので、強制終了されても OS が解放する。古い `.sock`
  は次の起動時に消してから作り直す。DISPLAY ごとに別なので、ssh -X 先などでは別に開ける。
  テストで本物を起動する時は `XDG_RUNTIME_DIR` を別にするか `--new-instance` を使う。
- **エラー表示**：`source.query()` が例外を出すと状態行に `Error: <short_error()>` を表示しつつ
  ポーリングは継続（`root.after` で再呼出）。GPU消失等に一時的に表示が空になるのは想定内。
  例外の全文（nvidia-smi の stderr 含む）は stderr に出す。毎回出すと端末が埋まるので、
  内容が前回と同じなら出さない（`_last_error`）。
- **不透明度**：`wm_attributes("-alpha")` は X11 の `_NET_WM_WINDOW_OPACITY` を設定するだけなので、
  コンポジタの無いウィンドウマネージャでは効かない（GNOME では効く）。
- **文字サイズ**：フォントは `Style` の名前付きフォントなので、ヘッダーや状態行は `configure(size=...)`
  だけで変わる。バー・グラフはピクセル寸法を作成時に決めるため、`_relayout()` でカードを作り直す。
  % 欄の幅は固定値ではなくフォントで "100%" を実測するので、どのサイズでも切れない。
- **更新間隔とグラフ**：グラフは常に `GRAPH_SECONDS` 秒分。間隔を変えると点数（`graph_points`）が変わるので、
  全 History を `resize()` する（新しい値は残る）。
- **pipx でのインストール**：`py-modules = ["gpu_monitor"]` の 1 ファイルだけを入れるので、`icon.png` は入らず
  ウィンドウアイコンは既定のまま（`ICON_FILE` が無ければ黙って既定にする）。メニュー登録とアイコンは
  clone して `install.sh`。Tkinter は pip では入らないので、Ubuntu では `python3-tk` が必要。
- **シグナル**：SIGINT / SIGTERM のハンドラは `root.after(0, close)` で予約するだけ。
  Tk の操作はメインループから行う。
- **アイコン**：原本は `icon.svg`。色はアプリと同じ（`BG` / `CARD_BG` / `BAR_BG` / `GOOD` / `WARN` / `BAD` / `DIM`）、
  バーの長さは 55% / 80% / 95% で、緑・黄・赤の閾値の意味と合わせてある。
  Tk 8.6 は SVG を読めないので、ウィンドウ用に PNG を作って同梱している。編集したら作り直す:
  `convert -background none icon.svg PNG32:icon.png`（ImageMagick）
- **Dock との対応付け**：GNOME はウィンドウの WM_CLASS と .desktop の `StartupWMClass` を照合して
  Dock のアイコンと名前を決める。Tk は既定で WM_CLASS が `Tk` になり対応付かないため、
  `className=WM_CLASS` で `gpu-monitor` / `Gpu-monitor` にしている。2 個目に起動したウィンドウは
  インスタンス名が `gpu-monitor #2` になるが、クラス名 `Gpu-monitor` で一致する。
  Tk は起動通知を送らないので `StartupNotify=false`（無いと起動後しばらく待ちカーソルになる）。
- **install.sh と Python のパス**：メニューから起動するとターミナルの PATH（pyenv や conda）が
  効かず、`/usr/bin/python3` に tkinter が無いこともある。そのため install.sh は
  tkinter が使える `python3` の絶対パスを `Exec=` に書き込む。

---

## 4. テスト手順

```bash
# 0) 自動テスト（GPU 不要。画面が無い環境では xvfb-run を付ける）
cd ~/programs/gpu_monitor
python3 -m unittest discover -s tests -v
#    GitHub に push すると .github/workflows/test.yml が同じテストと pipx install を実行する

# 0b) パッケージ（pipx と同じ形で入るか）
python3 -m pip wheel --no-deps -w /tmp/dist .
python3 -m venv /tmp/gm-venv && /tmp/gm-venv/bin/pip install /tmp/dist/gpu_monitor-*.whl
/tmp/gm-venv/bin/gpu-monitor --version

# 1) 起動
./gpu_monitor.py              # 通常起動（前回の「常に手前」状態と位置を引き継ぐ）
./gpu_monitor.py -A           # 「常に手前」を強制して起動
./gpu_monitor.py --help       # CLI 一覧

# 2) NVML と nvidia-smi で同じ値が出ること
./gpu_monitor.py                  # NVML
./gpu_monitor.py --nvidia-smi     # nvidia-smi
nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,memory.total,memory.used,power.draw,power.limit \
           --format=csv,noheader,nounits

# 3) 負荷を掛けてバー・色の反応を確認
#    (例: ffmpeg / stress-ng / 動画再生)

# 3b) 表示の確認
#    - カードにマウスを乗せる → 左にプロセス一覧。離すと消える
#    - 右クリック / ⋮ → メニュー。グラフ・コンパクト表示・文字サイズ・更新間隔・不透明度が次回も残ること
#    - もう一度 ./gpu_monitor.py → 新しいウィンドウは出ず、既存のものが前に出る

# 4) アイコンと WM_CLASS（Dock に GPU Monitor のアイコンが出ること）
xprop WM_CLASS     # ウィンドウをクリック → "gpu-monitor", "Gpu-monitor"

# 5) 設定の永続確認
#    - GUI上で「常に手前」を ON にして終了 → 再起動で ON のまま
#    - ウィンドウを動かして ✕ / Ctrl+C で終了 → 再起動で同じ位置
#    - ./gpu_monitor.py -R → 右上に戻る
#    - ~/.config/gpu_monitor.json の x を 9000 にして起動 → 右上に出る

# 6) 高負荷・エラー時の表示（偽の nvidia-smi を PATH の先頭に置き、--nvidia-smi で起動）
mkdir -p /tmp/fake_smi && cd /tmp/fake_smi
printf '#!/bin/sh\necho "0, Fake GPU, 85, 95, 8192, 8192, 230, 230"\n' > nvidia-smi  # 95%/100% の %、85°C が黄色
# printf '#!/bin/sh\nexit 9\n' > nvidia-smi     # → Error: nvidia-smi failed (exit 9)
# printf '#!/bin/sh\nsleep 30\n' > nvidia-smi   # → Error: nvidia-smi timed out (2s)
# printf '#!/bin/sh\nexit 0\n' > nvidia-smi     # → 0 GPUs（ウィンドウを動かせること）
chmod +x nvidia-smi
PATH=/tmp/fake_smi:$PATH ~/programs/gpu_monitor/gpu_monitor.py --nvidia-smi --new-instance

# 7) install.sh（一時ディレクトリに書き出して確認）
XDG_DATA_HOME=/tmp/xdg/data XDG_CONFIG_HOME=/tmp/xdg/config ./install.sh --autostart
desktop-file-validate /tmp/xdg/data/applications/gpu-monitor.desktop
find /tmp/xdg -type f          # .desktop 2 個 + アイコン 2 個
XDG_DATA_HOME=/tmp/xdg/data XDG_CONFIG_HOME=/tmp/xdg/config ./install.sh --uninstall
```

---

## 5. リリース手順

開発中は `CHANGELOG.md` の先頭を `## [x.y.z] - Unreleased` にして、`__version__` も同じ番号にしておく。
リリースするときは:

1. `CHANGELOG.md` の `Unreleased` をリリース日（例 `2026-12-01`）に書き換える。
2. テストを通してコミットし、タグを付けて push する。

```bash
python3 -m unittest discover -s tests
python3 scripts/release_notes.py v1.1.0      # リリース本文の確認（失敗したら直す）
git commit -am "Release 1.1.0"
git tag -a v1.1.0 -m "GPU Monitor 1.1.0"
git push && git push origin v1.1.0
```

3. タグの push で `.github/workflows/release.yml` が動き、テスト（test.yml）が通れば
   `scripts/release_notes.py` で取り出した CHANGELOG の節を本文にして GitHub のリリースを作る。
   タグと `__version__` が違う、CHANGELOG に節が無い、日付が `Unreleased` のまま、のどれかなら
   リリースは作られない（Actions のログにエラーが出る）。手作業は不要。

---

## 6. 将来の拡張候補

- [x] GPU 数変動（eGPU の接続、ドライバの再読み込み等）をポーリング内で検出しカードを自動再構築
- [ ] CPU / RAM 表示タブ（`/proc/stat` / `/proc/meminfo` 取得）
- [x] 温度・使用率の時間変化グラフ（canvas 描画、直近 60 秒）
- [ ] 色テーマ（dark/light）切替 + 設定ファイルに保存
- [x] ログイン時の自動起動（`install.sh --autostart`、XDG autostart）
- [ ] システムトレイへの常駐化（`pystray` 等）
- [ ] 閾値を超えたときのサウンド / 通知（`notify-send`）
- [ ] 使用率ログのCSV出力（長時間の観測・解析用）
