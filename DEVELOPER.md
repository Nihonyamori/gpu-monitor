# GPU Monitor — 開発者向けドキュメント

NVIDIA GPU の負荷（GPU使用率・メモリ使用率・消費電力・温度・メモリ絶対値）をリアルタイムに表示する小型 tkinter GUI プログラムの実装説明と、今後修正するための情報。

- ソース: `gpu_monitor.py`（全ロジックを1ファイルに集約）
- 依存: Python 3 標準ライブラリ（`tkinter` / `subprocess` / `argparse` / `json` / `pathlib` / `sys`）+ `nvidia-smi`（NVIDIA ドライバ同梱）
- 追加のパッケージは不要。

---

## 1. ファイル構成

```
programs/gpu_monitor/
├── gpu_monitor.py     # 本体（全ロジックを1ファイルに集約）
├── README.md          # 概要（英語・日本語）
├── USER.md            # ユーザ向け説明（英語）
├── USER_J.md          # ユーザ向け説明（日本語）
├── DEVELOPER.md       # このファイル（開発者向け）
├── gpu_monitor.png    # README 用スクリーンショット
└── LICENSE            # MIT License

実行時に自動生成:
~/.config/gpu_monitor.json   # 設定（現在「常に手前」の ON/OFF 状態のみ）
```

---

## 2. モジュール構造（gpu_monitor.py）

### 2-1. モジュール上定数（docstring と import の直後）

| 定数 | 意味 | 既定値 |
|---|---|---|
| `REFRESH_MS` | 更新間隔 (ms) | `500` |
| `QUERY_TIMEOUT_S` | nvidia-smi のタイムアウト (s) | `2` |
| `CONFIG_FILE` | 設定ファイルパス | `~/.config/gpu_monitor.json` |
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
    存在しない/壊れている場合は空辞書 {} を返す（起動は止めない）。

save_config(cfg: dict)
    同上ファイルへ JSON 書き込み。失敗しても例外を投げない（静かに無視）。
    key: "always_on_top" (bool)   # 現在この1項目のみ

color_for_pct(pct) -> str
    使用率から色を返す。
      pct >= 90  -> BAD  (赤)
      pct >= 70  -> WARN (黄)
      それ以下   -> GOOD (緑)

query_gpus() -> list[dict]
    nvidia-smi を叩いて全GPUの情報を取得する唯一のデータ取得口。
    各要素の dict キー（GUI側がこれを読む）:
      name         str    GPU名 (例 "NVIDIA GeForce RTX 3090")
      temp         float  温度 (°C)
      util         float  GPU 使用率 %
      mem_total    float  メモリ総量 (MiB)
      mem_used     float  メモリ使用量 (MiB)
      mem_pct      float  メモリ使用率 % (mem_used/mem_total*100)
      power        float  消費電力 (W)
      power_limit  float  電力上限 (W)
      power_pct    float  消費電力率 % (power/power_limit*100)
    裏のコマンド:
      nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,\
                            memory.total,memory.used,power.draw,power.limit \
                  --format=csv,noheader,nounits
    QUERY_TIMEOUT_S 秒で応答がなければ subprocess.TimeoutExpired。
    例外はここでは捕捉せず、refresh() 側で処理する。

short_error(e) -> str
    query_gpus() の例外を状態行用の短い 1 行にする。
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
    1GPU分のカード(Frame)。
    .util_bar  BarWidget (GPU使用率)
    .mem_bar   BarWidget (メモリ使用率)
    .pwr_bar   BarWidget (消費電力率)
    .detail    tk.Label ("XXX/YYY MiB  ZZ°C  P/Q W" の行)
    .update(g) query_gpus() の dict 1件を受け取って全項目を反映

class App(always_on_top=None)
    メインウィンドウ。
    __init__  既定(None)なら load_config() の状態を採用。ヘッダー・トグル
              ボタン・カード枠・状態行を作成し、refresh() を開始。
    .top_btn      「常に手前」トグルボタン
    .cards        GpuCard のリスト
    ._toggle_topmost()  トグル押下 → 状態反転 + save_config() で永続化
    ._initial_place()   内容に合わせたサイズでウィンドウを右上に配置。
                        最初の取得成功時に 1 回だけ（_placed フラグ）
    ._fit()             更新毎にウィンドウサイズを内容に追随（位置は保持）
    .refresh()          500ms ごとに nvidia-smi 取得 → 全カード更新 →
                        self.root.after(REFRESH_MS, ...) で再帰スケジュール

main()
    argparse で CLI をパースして App(...).root.mainloop() を起動。
```

### 2-3. 起動フロー

```
main()
  └─> App(always_on_top).root.mainloop()
         ├─> refresh()            (nvidia-smi コール #1)
         │      ├─ エラーなら状態行に short_error() を出して次回へ
         │      ├─ カード未生成なら GpuCard 生成 x N
         │      ├─ 未配置なら _initial_place()（1 回だけ）
         │      ├─ card.update(g) を各GPUへ
         │      └─ root.after(REFRESH_MS, refresh)   ← 再ポーリング
         └─> mainloop             (イベントループ)
```

### 2-4. 状態保持

- 保存されるのは「常に手前」(always-on-top) の ON/OFF 1項目のみ。
  → `~/.config/gpu_monitor.json`（例: `{"always_on_top": true}`）
- ウィンドウ位置・サイズ・色テーマ等は**未保存**（毎回初期値）。
  必要なら `load_config()` / `save_config(cfg)` に key を追加するだけ。
- **ウィンドウ幅調整**: `_initial_place()` で初期配置、`_fit()` で内容幅に追随（余白無し）。
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
| 表示項目追加 | `query_gpus()` の dict にキー追加 → `GpuCard.update(g)` で描画 |
| 消費電力の表示/閾値 | `query_gpus()` の `power.draw/power.limit`・`GpuCard` の `pwr_bar` |
| nvidia-smi の別項目 | `query_gpus()` の `--query-gpu=` 列 + `dict(...)` の追加 |
| 複数/動的 GPU | `App.refresh()` の初回カード生成部（今は初回スキャン時の数で固定） |
| 常に手前の初期値 | `load_config()` の既定 or `~/.config/gpu_monitor.json` |
| ウィンドウ幅・配置 | `App._initial_place()` / `App._fit()` / `root.geometry` |
| 常時手前以外の新規状態の永続 | `load_config`/`save_config` に key 追加 + 使用箇所 |

### 設計上の注意

- **tkinter のシングルスレッド前提**：GPU 取得は一発の `subprocess` 呼出なのでそのまま同期呼び出し
  （GTX 1070 + RTX 3090 の環境で 1 回 30〜40ms）。`nvidia-smi` が固まった場合に備えて
  `QUERY_TIMEOUT_S` で打ち切る（その間は GUI が止まる）。
  長い処理（外部API等）を入れる場合は `threading` で取り、結果は `root.after` でUIスレッドへ戻すパターンが安全。
- **nvidia-smi 依存**：ドライバ未構築環境ではカードは作られず、状態行に
  `Error: nvidia-smi not found` を表示する。
- **GPU 0 枚**：カードは作られず「0 GPUs」と表示。カード生成は GPU が見つかるまで毎回再試行する。
- **GPU の動的増減は未サポート**：カード生成は GPU が 1 枚以上見つかった最初の `refresh()` で1回だけ。
  実行中に GPU 数が変わっても自動再構築されない。必要ならポーリング内で
  `len(self.cards) != len(gpu_list)` を検出してカードを再構築するロジックを追加。
- **エラー表示**：`query_gpus()` が例外を出すと状態行に `Error: <short_error()>` を表示しつつ
  ポーリングは継続（`root.after` で再呼出）。GPU消失等に一時的に表示が空になるのは想定内。
  例外の全文（nvidia-smi の stderr 含む）は stderr に出す。毎回出すと端末が埋まるので、
  内容が前回と同じなら出さない（`_last_error`）。

---

## 4. テスト手順

```bash
# 1) 起動
cd ~/programs/gpu_monitor
./gpu_monitor.py            # 通常起動（前回の「常に手前」状態を引き継ぐ）
./gpu_monitor.py -A         # 「常に手前」を強制して起動
./gpu_monitor.py --help     # CLI 一覧

# 2) nvidia-smi が正しく動くこと
nvidia-smi --query-gpu=index,name,temperature.gpu,utilization.gpu,memory.total,memory.used,power.draw,power.limit \
           --format=csv,noheader,nounits

# 3) 負荷を掛けてバー・色の反応を確認
#    (例: ffmpeg / stress-ng / 動画再生)

# 4) 「常に手前」の永続確認
#    - GUI上で ON にして終了 → ~/.config/gpu_monitor.json が {"always_on_top": true}
#    - 再起動 → 自動で ON のままである

# 5) 高負荷・エラー時の表示（偽の nvidia-smi を PATH の先頭に置く）
mkdir -p /tmp/fake_smi && cd /tmp/fake_smi
printf '#!/bin/sh\necho "0, Fake GPU, 80, 95, 8192, 8192, 230, 230"\n' > nvidia-smi  # 95%/100% の % が読めるか
# printf '#!/bin/sh\nexit 9\n' > nvidia-smi     # → Error: nvidia-smi failed (exit 9)
# printf '#!/bin/sh\nsleep 30\n' > nvidia-smi   # → Error: nvidia-smi timed out (2s)
# printf '#!/bin/sh\nexit 0\n' > nvidia-smi     # → 0 GPUs（ウィンドウを動かせること）
chmod +x nvidia-smi
PATH=/tmp/fake_smi:$PATH ~/programs/gpu_monitor/gpu_monitor.py
```

---

## 5. 将来の拡張候補

- [ ] GPU 数変動（eGPU の接続、ドライバの再読み込み等）をポーリング内で検出しカードを自動再構築
- [ ] CPU / RAM 表示タブ（`/proc/stat` / `/proc/meminfo` 取得）
- [ ] 温度・使用率の時間変化ヒストグラム（canvas 描画）
- [ ] 色テーマ（dark/light）切替 + 設定ファイルに保存
- [ ] `systemd` ユーザサービスでの自動起動
- [ ] システムトレイへの常駐化（`pystray` 等）
- [ ] 閾値を超えたときのサウンド / 通知（`notify-send`）
- [ ] 使用率ログのCSV出力（長時間の観測・解析用）
