# GPU Monitor — 開発者向けドキュメント

NVIDIA GPU の負荷（GPU使用率・メモリ使用率・消費電力・温度・メモリ絶対値）をリアルタイムに表示する小型 tkinter GUI プログラムの実装説明と、今後修正するための情報。

- ソース: `gpu_monitor.py`（全ロジックを1ファイルに集約 / 約 236 行）
- 依存: Python 3 標準ライブラリ（`tkinter` / `subprocess` / `argparse` / `json`）+ `nvidia-smi`（NVIDIA ドライバ同梱）
- 追加のパッケージは不要。

---

## 1. ファイル構成

```
programs/gpu_monitor/
├── gpu_monitor.py     # 本体（全ロジックを1ファイルに集約）
├── DEVELOPER.md       # このファイル（開発者向け）
└── USER.md            # ユーザ向け説明

実行時に自動生成:
~/.config/gpu_monitor.json   # 設定（現在「常に手前」の ON/OFF 状態のみ）
```

---

## 2. モジュール構造（gpu_monitor.py）

### 2-1. モジュール上定数（25〜35行付近）

| 定数 | 意味 | 既定値 |
|---|---|---|
| `REFRESH_MS` | 更新間隔 (ms) | `500` |
| `CONFIG_FILE` | 設定ファイルパス | `~/.config/gpu_monitor.json` |
| `BAR_W` / `BAR_H` | 使用率バーの幅 / 高 (px) | `190` / `14` |
| `WIN_W` | ウィンドウ幅 (px) | `350` |
| `CARD_H` | GPU カード1枚の高（概算, px） | `132` |
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

class BarWidget(parent, row, label_text)
    1本の「横バー + パーセント表示」。
    .label   tk.Label ("GPU"/"MEM")
    .canvas  tk.Canvas (バー本体)
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
    ._initial_place()   GPU数に応じた高でウィンドウを(初期)右上に配置
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
         │      ├─ 初回なら GpuCard 生成 x N + _initial_place()
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

- **tkinter のシングルスレッド前提**：GPU 取得は一発の `subprocess` 呼出なのでそのまま同期呼び出し。
  長い処理（外部API等）を入れる場合は `threading` で取り、結果は `root.after` でUIスレッドへ戻すパターンが安全。
- **nvidia-smi 依存**：ドライバ未構築環境では全カードが `--` のまま。
  `shutil.which("nvidia-smi")` で存在確認し、起動時に明示メッセージを出すのも手。
- **GPU の動的増減は未サポート**：カード生成は初回 `refresh()` で1回だけ。
  実行中に GPU 数が変わっても自動再構築されない。必要ならポーリング内で
  `len(self.cards) != len(gpu_list)` を検出してカードを再構築するロジックを追加。
- **エラー表示**：`query_gpus()` が例外を出すと状態行に「エラー: ...」を表示しつつ
  ポーリングは継続（`root.after` で再呼出）。GPU消失等に一時的に表示が空になるのは想定内。

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
```

---

## 5. 将来の拡張候補

- [ ] GPU 数変動（HDMIホットプラグ等）をポーリング内で検出しカードを自動再構築
- [ ] CPU / RAM 表示タブ（`/proc/stat` / `/proc/meminfo` 取得）
- [ ] 温度・使用率の時間変化ヒストグラム（canvas 描画）
- [ ] 色テーマ（dark/light）切替 + 設定ファイルに保存
- [ ] `systemd` ユーザサービスでの自動起動
- [ ] システムトレイへの常駐化（`pystray` 等）
- [ ] 閾値を超えたときのサウンド / 通知（`notify-send`）
- [ ] 使用率ログのCSV出力（長時間の観測・解析用）
