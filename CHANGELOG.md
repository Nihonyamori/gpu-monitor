# Changelog / 変更履歴

The version number is `__version__` in `gpu_monitor.py` (also shown by `--version` and at the bottom of the menu). Keep this file in sync with it; a test checks that the current version is listed here.

バージョン番号は `gpu_monitor.py` の `__version__`（`--version` とメニューの最下段にも表示）。このファイルと揃えること（テストで確認している）。

## [1.0.0] - 2026-11-05

### Added / 追加
- Read GPU data directly from NVML via ctypes; fall back to `nvidia-smi` (`--nvidia-smi` forces it). / NVML を ctypes で直接読む。使えなければ `nvidia-smi`（`--nvidia-smi` で強制）
- Process list when the mouse is over a GPU card (PID, user, memory, type, command). / カードにマウスを乗せると、その GPU のプロセス一覧（PID・ユーザ・メモリ・種類・コマンド）
- 60-second history graph of GPU utilization and temperature. / 直近 60 秒の GPU 使用率と温度のグラフ
- Compact view: one line per GPU. / コンパクト表示（1 GPU 1 行）
- Window opacity (100–60%). / ウィンドウの不透明度（100〜60%）
- Menu from right-click or the "⋮" button: always on top, compact view, graph, opacity, move to top-right, quit, version. / 右クリックか「⋮」ボタンのメニュー：常に手前・コンパクト表示・グラフ・不透明度・右上へ移動・終了・バージョン
- Temperature turns yellow from 80°C and red from 90°C. / 温度は 80°C 以上で黄、90°C 以上で赤
- Remember the window position, graph, compact view and opacity; `-R` resets the position. / ウィンドウ位置・グラフ・コンパクト表示・不透明度を記憶。`-R` で位置をリセット
- Single instance per user and display; a second launch brings the window to the front (`--new-instance` to open another). / 二重起動しない。2 回目は既存のウィンドウを手前に（`--new-instance` で別に開く）
- Rebuild the cards when GPUs are added or removed. / GPU の増減に追従
- App icon, WM_CLASS and `install.sh` for the application menu and autostart. / アイコン、WM_CLASS、メニュー・自動起動に登録する `install.sh`
- `--no-always-on-top`, `--version`. / `--no-always-on-top`、`--version`
- Unit tests (no GPU needed) and GitHub Actions. / 自動テスト（GPU 不要）と GitHub Actions

### Changed / 変更
- Memory is shown in GiB. / メモリは GiB 表示
- The percentage is drawn right of the bar. / % はバーの右に表示
- Cards show the GPU index reported by the driver; "1 GPU" in singular. / カード番号はドライバの index。1 枚なら "1 GPU"

### Fixed / 修正
- Percentage unreadable at 90% or more, and "100%" clipped. / 90% 以上で % が読めない・"100%" が切れる
- A long error message widened the window permanently. / 長いエラーでウィンドウが横長のまま戻らない
- The GUI froze when `nvidia-smi` hung (2 s timeout). / `nvidia-smi` が固まると GUI も止まる（2 秒で打ち切り）
- The window could not be moved while no GPU was found. / GPU 0 枚のときウィンドウを動かせない
- The window drifted down by the title-bar height when its size changed. / サイズが変わるとタイトルバーの高さ分ずつ下にずれる

## [0.1.0] - 2026-11-05

- First version: GPU / MEM / PWR bars per GPU, detail line, always on top, bilingual docs. / 最初の版：GPU ごとの GPU / MEM / PWR バー、詳細行、常に手前、日英の文書
