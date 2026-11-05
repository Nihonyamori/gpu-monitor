# GPU Monitor — 開発者向けドキュメント

NVIDIA GPU の負荷（GPU使用率・メモリ使用率・消費電力・温度・メモリ絶対値）をリアルタイムに表示する小型 tkinter GUI プログラムの実装説明と、今後修正するための情報。

- ソース: `gpu_monitor.py`（全ロジックを1ファイルに集約）
- 依存: Python 3 標準ライブラリ（`tkinter` / `ctypes` / `subprocess` / `argparse` / `json` / `pathlib` / `re` / `signal` / `sys`）+ NVIDIA ドライバ（`libnvidia-ml.so.1` か `nvidia-smi`）
- 追加のパッケージは不要。

---

## 1. ファイル構成

```
programs/gpu_monitor/
├── gpu_monitor.py     # 本体（全ロジックを1ファイルに集約）
├── install.sh         # アプリメニュー・自動起動への登録 / 削除
├── README.md          # 概要（英語・日本語）
├── USER.md            # ユーザ向け説明（英語）
├── USER_J.md          # ユーザ向け説明（日本語）
├── DEVELOPER.md       # このファイル（開発者向け）
├── gpu_monitor.png    # README 用スクリーンショット
└── LICENSE            # MIT License

実行時に自動生成:
~/.config/gpu_monitor.json   # 設定（「常に手前」の ON/OFF とウィンドウ位置）

install.sh が生成:
~/.local/share/applications/gpu-monitor.desktop   # アプリメニュー
~/.config/autostart/gpu-monitor.desktop           # 自動起動（--autostart 時）
```

---

## 2. モジュール構造（gpu_monitor.py）

### 2-1. モジュール上定数（docstring と import の直後）

| 定数 | 意味 | 既定値 |
|---|---|---|
| `REFRESH_MS` | 更新間隔 (ms) | `500` |
| `QUERY_TIMEOUT_S` | nvidia-smi のタイムアウト (s) | `2` |
| `CONFIG_FILE` | 設定ファイルパス | `~/.config/gpu_monitor.json` |
| `NVML_LIB` | NVML の共有ライブラリ名 | `libnvidia-ml.so.1` |
| `BAR_W` / `BAR_H` | 使用率バーの幅 / 高 (px) | `160` / `12` |
| `PCT_W` | バー右側の % 表示領域の幅 (px)。「100%」が収まる幅 | `34` |
| `BG` / `CARD_BG` | ウィンドウ背景 / カード背景 | `#1e1e2e` / `#2a2a3c` |
| `FG` / `DIM` | 前景テキスト / 薄めテキスト | `#e6e6f0` / `#9a9ab0` |
| `GOOD` / `WARN` / `BAD` | 低負荷 / 中負荷 / 高負荷の色 | 緑 / 黄 / 赤 |
| `BAR_BG` | バー未使用部の背景 | `#15151f` |

> テーマ変更はこの定数ブロックの HEX 値を差し替えるだけ。

### 2-2. 関数・クラス一覧

```
load_config() -> dict
    ~/.config/gpu_monitor.json を JSON で読込。
    存在しない/壊れている/dict でない場合は空辞書 {} を返す（起動は止めない）。

save_config(cfg: dict)
    同上ファイルへ JSON 書き込み。失敗しても例外を投げない（静かに無視）。
    key: "always_on_top" (bool), "x" / "y" (int, ウィンドウ位置)

color_for_pct(pct) -> str
    使用率から色を返す。
      pct >= 90  -> BAD  (赤)
      pct >= 70  -> WARN (黄)
      それ以下   -> GOOD (緑)

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

query_gpus() -> list[dict]
    nvidia-smi で全GPUの情報を取得する（SmiSource の中身）。
    裏のコマンド:
      nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,\
                            memory.total,memory.used,power.draw,power.limit \
                  --format=csv,noheader,nounits
    QUERY_TIMEOUT_S 秒で応答がなければ subprocess.TimeoutExpired。
    例外はここでは捕捉せず、refresh() 側で処理する。

class SmiSource          name = "nvidia-smi"
    .query()  query_gpus() を呼ぶだけ
    .close()  何もしない

class NvmlSource         name = "NVML"
    ctypes で libnvidia-ml.so.1 を直接呼ぶ。プロセス起動がなく 1 回約 2ms。
    __init__  ライブラリ読込 + nvmlInit_v2。失敗時は OSError / NvmlError。
    .query()  nvmlDeviceGetCount_v2 → GPU ごとに Name / UtilizationRates /
              Temperature / PowerUsage / PowerManagementLimit / MemoryInfo。
              メモリは v2 API（予約領域を除く使用量で nvidia-smi と一致）、
              v2 が無い古いドライバでは v1。
              NOT_SUPPORTED は 0 扱い、それ以外のエラーは NvmlError。
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

class BarWidget(parent, row, label_text)
    1本の「横バー + パーセント表示」。
    .label   tk.Label ("GPU"/"MEM"/"PWR")
    .canvas  tk.Canvas (幅 BAR_W + PCT_W)。0〜BAR_W にバー、その右の
             PCT_W 部分に % を右寄せで描く。% をバーの外に置くので、
             90% 以上（赤）でも塗りと重ならず読める
    .rect / .txt  canvas 内の図形ID
    .set(pct)  幅・色・数値を 1 度に更新 (0〜100 にクランプ)

class GpuCard(parent, idx, name)
    1GPU分のカード(Frame)。タイトルは "GPU <index>  <name>"。
    .util_bar  BarWidget (GPU使用率)
    .mem_bar   BarWidget (メモリ使用率)
    .pwr_bar   BarWidget (消費電力率)
    .detail    tk.Label ("XXX/YYY MiB  ZZ°C  P/Q W" の行)
    .update(g) make_gpu() の dict 1件を受け取って全項目を反映

class App(source, always_on_top=None, reset_position=False)
    メインウィンドウ。
    __init__  always_on_top が None なら設定ファイルの値を採用。
              reset_position でなければ保存位置 (x, y) を覚えておく。
              ヘッダー・トグルボタン・カード枠・状態行を作成し、refresh() を開始。
    .source       データソース（NvmlSource / SmiSource）
    .top_btn      「常に手前」トグルボタン
    .cards        GpuCard のリスト
    ._toggle_topmost()  トグル押下 → 状態反転 + save_config() で永続化
    ._place_once()      初回の refresh で 1 回だけ配置（成功・エラーどちらでも）。
                        保存位置が画面内（50px 以上見える）ならそこ、
                        そうでなければ右上。サイズは内容に合わせる
    ._fit()             更新毎にウィンドウサイズを内容に追随。
                        サイズだけ指定し、位置はウィンドウマネージャに任せる
    .close()            位置を保存 → source.close() → root.destroy()。
                        閉じるボタンと SIGINT / SIGTERM から呼ばれる（2 回目以降は無視）
    .refresh()          500ms ごとに source.query() → 全カード更新 →
                        self.root.after(REFRESH_MS, ...) で再帰スケジュール

main()
    argparse で CLI をパース（-A / --no-always-on-top / -R / --nvidia-smi）。
    open_source() でソースを選び App を作成、SIGINT / SIGTERM で close()
    を予約するハンドラを登録してから mainloop()。
```

### 2-3. 起動フロー

```
main()
  ├─> open_source()          NVML → 失敗なら nvidia-smi
  └─> App(source, ...).root.mainloop()
         ├─> refresh()            (source.query() #1)
         │      ├─ エラーなら状態行に short_error() を出し、_place_once() して次回へ
         │      ├─ カード未生成なら GpuCard 生成 x N
         │      ├─ card.update(g) を各GPUへ
         │      ├─ _place_once()（1 回だけ）→ _fit()
         │      └─ root.after(REFRESH_MS, refresh)   ← 再ポーリング
         └─> mainloop             (イベントループ)
               └─ ✕ / Ctrl+C / kill → close()  位置を保存して終了
```

### 2-4. 状態保持

- 保存されるのは「常に手前」(always-on-top) の ON/OFF とウィンドウ位置。
  → `~/.config/gpu_monitor.json`（例: `{"always_on_top": true, "x": 2932, "y": 20}`）
  - `always_on_top` はボタンを押したときに保存。`-A` / `--no-always-on-top` は保存しない。
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
| 更新間隔変更 | `REFRESH_MS` |
| nvidia-smi のタイムアウト | `QUERY_TIMEOUT_S` |
| バー・% 表示の幅 | `BAR_W` / `PCT_W` |
| エラーメッセージ | `short_error(e)` |
| 色テーマ変更 | `BG` / `CARD_BG` / `GOOD` / `WARN` / `BAD` 等のHEX |
| 黄/赤の閾値変更 | `color_for_pct(pct)`（`>=90` / `>=70` の数字） |
| 表示項目追加 | `make_gpu()` にキー追加 → 両ソース（`NvmlSource.query()` / `query_gpus()`）で値を取得 → `GpuCard.update(g)` で描画 |
| 消費電力の表示/閾値 | `NvmlSource.query()` の PowerUsage / PowerManagementLimit、`query_gpus()` の `power.draw/power.limit`、`GpuCard` の `pwr_bar` |
| データソースの選択 | `open_source()` / `--nvidia-smi` |
| 複数/動的 GPU | `App.refresh()` のカード生成部（今は最初に見つかった数で固定） |
| 常に手前の初期値 | `load_config()` の既定 or `~/.config/gpu_monitor.json` |
| ウィンドウ幅・配置 | `App._place_once()` / `App._fit()` / `root.geometry` |
| 終了時の処理 | `App.close()` |
| 新規状態の永続 | `load_config`/`save_config` に key 追加 + 使用箇所 |
| メニュー項目の内容 | `install.sh` の `[Desktop Entry]` |

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
- **GPU 0 枚**：カードは作られず「0 GPUs」と表示。カード生成は GPU が見つかるまで毎回再試行する。
- **GPU の動的増減は未サポート**：カード生成は GPU が 1 枚以上見つかった最初の `refresh()` で1回だけ。
  実行中に GPU 数が変わっても自動再構築されない。必要ならポーリング内で
  `len(self.cards) != len(gpu_list)` を検出してカードを再構築するロジックを追加。
- **エラー表示**：`source.query()` が例外を出すと状態行に `Error: <short_error()>` を表示しつつ
  ポーリングは継続（`root.after` で再呼出）。GPU消失等に一時的に表示が空になるのは想定内。
  例外の全文（nvidia-smi の stderr 含む）は stderr に出す。毎回出すと端末が埋まるので、
  内容が前回と同じなら出さない（`_last_error`）。
- **シグナル**：SIGINT / SIGTERM のハンドラは `root.after(0, close)` で予約するだけ。
  Tk の操作はメインループから行う。
- **install.sh と Python のパス**：メニューから起動するとターミナルの PATH（pyenv や conda）が
  効かず、`/usr/bin/python3` に tkinter が無いこともある。そのため install.sh は
  tkinter が使える `python3` の絶対パスを `Exec=` に書き込む。

---

## 4. テスト手順

```bash
# 1) 起動
cd ~/programs/gpu_monitor
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

# 4) 設定の永続確認
#    - GUI上で「常に手前」を ON にして終了 → 再起動で ON のまま
#    - ウィンドウを動かして ✕ / Ctrl+C で終了 → 再起動で同じ位置
#    - ./gpu_monitor.py -R → 右上に戻る
#    - ~/.config/gpu_monitor.json の x を 9000 にして起動 → 右上に出る

# 5) 高負荷・エラー時の表示（偽の nvidia-smi を PATH の先頭に置き、--nvidia-smi で起動）
mkdir -p /tmp/fake_smi && cd /tmp/fake_smi
printf '#!/bin/sh\necho "0, Fake GPU, 80, 95, 8192, 8192, 230, 230"\n' > nvidia-smi  # 95%/100% の % が読めるか
# printf '#!/bin/sh\nexit 9\n' > nvidia-smi     # → Error: nvidia-smi failed (exit 9)
# printf '#!/bin/sh\nsleep 30\n' > nvidia-smi   # → Error: nvidia-smi timed out (2s)
# printf '#!/bin/sh\nexit 0\n' > nvidia-smi     # → 0 GPUs（ウィンドウを動かせること）
chmod +x nvidia-smi
PATH=/tmp/fake_smi:$PATH ~/programs/gpu_monitor/gpu_monitor.py --nvidia-smi

# 6) install.sh（一時ディレクトリに書き出して確認）
XDG_DATA_HOME=/tmp/xdg/data XDG_CONFIG_HOME=/tmp/xdg/config ./install.sh --autostart
desktop-file-validate /tmp/xdg/data/applications/gpu-monitor.desktop
XDG_DATA_HOME=/tmp/xdg/data XDG_CONFIG_HOME=/tmp/xdg/config ./install.sh --uninstall
```

---

## 5. 将来の拡張候補

- [ ] GPU 数変動（eGPU の接続、ドライバの再読み込み等）をポーリング内で検出しカードを自動再構築
- [ ] CPU / RAM 表示タブ（`/proc/stat` / `/proc/meminfo` 取得）
- [ ] 温度・使用率の時間変化ヒストグラム（canvas 描画）
- [ ] 色テーマ（dark/light）切替 + 設定ファイルに保存
- [x] ログイン時の自動起動（`install.sh --autostart`、XDG autostart）
- [ ] システムトレイへの常駐化（`pystray` 等）
- [ ] 閾値を超えたときのサウンド / 通知（`notify-send`）
- [ ] 使用率ログのCSV出力（長時間の観測・解析用）
