#!/usr/bin/env python3
"""
GPU Monitor
=======================
Author    : Takuya Saito
Created   : 2026-11-04

Japanese (概要):
  NVIDIA GPU のリアルタイム使用状況を小さく右上に常時表示する tkinter GUI。
  GPU 使用率・メモリ使用率・消費電力率・温度・メモリ絶対値を 0.5秒間隔で
  nvidia-smi から取得し、カード形式で表示する。

English (Summary):
  A tiny tkinter GUI that displays the real-time usage of all NVIDIA
  GPUs in a small window pinned to the top-right of the screen.
  GPU utilization, memory utilization, power draw ratio, temperature
  and memory size are fetched every 0.5 seconds from nvidia-smi and
  rendered as per-GPU cards.

Features (主な機能):
  - 複数 GPU に対応（検出された数だけカード生成）
    / Supports multiple GPUs (one card per detected GPU)
  - 各 GPU につき 3 本の水平バー: GPU / MEM / PWR
    / 3 horizontal bars per GPU: GPU / MEM / PWR
  - 色分け: <70% 緑、70-89% 黄、>=90% 赤
    / Color coding: green < 70%, yellow 70-89%, red >= 90%
  - 詳細行: 使用/総量 MiB, 温度 °C, 電力/上限 W を 1 行表示
    / Detail line: used/total MiB, temperature °C, power/limit W
  - 「Always on top」トグル。状態は ~/.config/gpu_monitor.json に
    永続保存され次回起動時に復元される。
    / "Always on top" toggle, persisted to ~/.config/gpu_monitor.json
    and restored on the next launch.
  - ウィンドウは内容にピッタリフィット（余白 0px）、幅は一度広がった
    ら縮まないよう安定化。画面右上に配置。
    / Window fits its content exactly (0px padding); width is stable
    (never shrinks); placed at the top-right of the screen.
  - 設定ファイル無くても起動可能（既定値へフォールバック）
    / Works even without a config file (falls back to defaults).

Dependencies (依存関係):
  - Python 3 standard library only (tkinter, subprocess, argparse,
    json, pathlib). No pip packages.
    / Python 3 標準ライブラリのみ（外部パッケージ不要）
  - NVIDIA driver with the `nvidia-smi` command available.
    / `nvidia-smi` が使える NVIDIA ドライバ

Usage (使い方):
  ./gpu_monitor.py                Normal start (restores last always-on-top)
                                  / 通常起動（前回の always-on-top を引き継ぐ）
  ./gpu_monitor.py -A             Start with always-on-top / 常時手前で起動
  ./gpu_monitor.py --help         Show help / ヘルプ表示

Design notes (設計上のポイント):
  - All logic in one file; no external packages.
    / 全ロジックを1ファイルに集約し、外部パッケージ不要。
  - UI runs on tkinter's main loop. nvidia-smi is called synchronously
    via subprocess (light enough for a 0.5s cadence), with a timeout
    so a hung nvidia-smi cannot freeze the GUI indefinitely.
    / UI スレッドは tkinter のメインループのみ。nvidia-smi は同期
      subprocess で起動（0.5s 間隔なら軽量）。nvidia-smi が固まっても
      GUI が止まり続けないよう timeout を付けている。
  - Window width is stabilized by caching the max requested width in
    self._max_req so it never shrinks back. Initial placement is done
    by _initial_place; subsequent updates are done by _fit.
    / ウィンドウ幅は _max_req に最大必須幅を保持することで縮小しない。
      初期配置は _initial_place、更新毎に _fit で内容に追随。
  - Persistence is just two small helpers: load_config / save_config.
    / 設定は load_config / save_config の 2 関数で JSON 永続化。
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import tkinter as tk

REFRESH_MS = 500   # Refresh interval in milliseconds / 更新間隔 (ms)
QUERY_TIMEOUT_S = 2  # nvidia-smi timeout in seconds / nvidia-smi のタイムアウト (s)
CONFIG_FILE = Path.home() / ".config" / "gpu_monitor.json"
BAR_W = 160        # Bar width in pixels / バー幅 (px)
BAR_H = 12         # Bar height in pixels / バー高さ (px)
PCT_W = 34         # Width of the "100%" text area right of the bar (px)
                   # / バー右側の % 表示領域の幅 (px)

# --- Colors (色) -------------------------------------------
BG = "#1e1e2e"       # Window background / ウィンドウ背景
CARD_BG = "#2a2a3c"  # Card background / カード背景
FG = "#e6e6f0"       # Normal foreground text / 通常テキスト
DIM = "#9a9ab0"      # Dimmed (secondary) text / サブテキスト
GOOD = "#4ade80"     # Green (<70%) / 緑（70%未満）
WARN = "#facc15"     # Yellow (70-89%) / 黄（70-89%）
BAD = "#f87171"      # Red (>=90%) / 赤（90%以上）
BAR_BG = "#15151f"   # Unused bar area / バー未使用エリア


def load_config():
    """Load the JSON config file.
    / JSON 設定ファイルを読み込む。

    Returns an empty dict if the file does not exist or is corrupted,
    so startup keeps working. / ファイルが無い・壊れている場合は空 dict
    を返し、起動を継続させる。Sample stored key: always_on_top (bool).
    """
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    """Persist the config dict to disk.
    / 設定 dict をディスクに書き込む。

    Failures are silently ignored so that UI behavior is never blocked
    by permission / IO issues. / 書き込み失敗は静かに無視する
    （権限・I/O 問題で UI を阻害しない）。
    """
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg))
    except OSError:
        pass


def color_for_pct(pct):
    """Map a usage percentage to a bar color.
    / 使用率 % からバーの色を返す。

    >= 90% red, 70-89% yellow, else green.
    / 90% 以上 = 赤、70% 以上 = 黄、それ未満 = 緑。
    """
    if pct >= 90:
        return BAD
    if pct >= 70:
        return WARN
    return GOOD


def query_gpus():
    """Fetch information for all NVIDIA GPUs.
    / 全 GPU の情報を取得する。

    Calls nvidia-smi once and parses a CSV response.
    / nvidia-smi を 1 回呼び出し、CSV で取得する。

    Returns a list of dicts with keys: / 戻り値は dict の list:
      name / name            GPU 名 / GPU name
      temp / temp            温度(°C) / Temperature (°C)
      util / util            GPU 使用率(%) / GPU utilization (%)
      mem_total / mem_used   メモリ総量/使用量(MiB) / Total/used memory (MiB)
      mem_pct                メモリ使用率(%) / Memory usage (%)
      power / power_limit    消費電力/上限(W) / Power draw / limit (W)
      power_pct              消費電力率(%) / Power draw ratio (%)

    Exceptions are intentionally let propagate; the caller will catch
    them and show the error in the status line. If nvidia-smi does not
    answer within QUERY_TIMEOUT_S, subprocess.TimeoutExpired is raised.
    / 例外は呼び出し元で捕捉し、状態行に表示する。nvidia-smi が
      QUERY_TIMEOUT_S 秒以内に応答しなければ TimeoutExpired を送出する。
    """
    out = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,temperature.gpu,utilization.gpu,"
            "memory.total,memory.used,power.draw,power.limit",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True, text=True, check=True,
        timeout=QUERY_TIMEOUT_S,
    ).stdout.strip()

    def num(s, default=0.0):
        """Parse a numeric string; return default on failure.
        / 数値文字列を float に変換。失敗時は default を返す。"""
        try:
            return float(s)
        except ValueError:
            return default

    gpus = []
    for line in out.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 6:
            continue
        # Memory fields (MiB) / メモリ関連フィールド (MiB)
        mem_total, mem_used = num(p[4]), num(p[5])
        # Power fields (W) - guard for older nvidia-smi / 消費電力 (W)
        power      = num(p[6]) if len(p) > 6 else 0.0
        power_lmt  = num(p[7]) if len(p) > 7 else 0.0
        gpus.append(dict(
            name=p[1],
            temp=num(p[2]),
            util=num(p[3]),
            mem_total=mem_total,
            mem_used=mem_used,
            mem_pct=(mem_used / mem_total * 100) if mem_total else 0.0,
            power=power,
            power_limit=power_lmt,
            power_pct=(power / power_lmt * 100) if power_lmt else 0.0,
        ))
    return gpus


def short_error(e):
    """Return a short one-line message for a query_gpus() exception.
    / query_gpus() の例外を、状態行用の短い 1 行メッセージにする。

    str(CalledProcessError) contains the whole argument list (~200
    chars) and would stretch the window, so it is never shown as is.
    / CalledProcessError の文字列は引数一覧を含み約 200 文字になり
      ウィンドウを横に引き伸ばすため、そのままは表示しない。
    """
    if isinstance(e, FileNotFoundError):
        return "nvidia-smi not found"
    if isinstance(e, subprocess.TimeoutExpired):
        return f"nvidia-smi timed out ({QUERY_TIMEOUT_S}s)"
    if isinstance(e, subprocess.CalledProcessError):
        return f"nvidia-smi failed (exit {e.returncode})"
    return type(e).__name__


class BarWidget:
    """A single horizontal usage bar with a percentage label.
    / パーセンテージラベル付きの水平バー1本。"""

    def __init__(self, parent, row, label_text):
        # Left-side label (GPU / MEM / PWR) / 左端のラベル
        self.label = tk.Label(parent, text=label_text, width=4, anchor="e",
                              bg=CARD_BG, fg=DIM, font=("Helvetica", 10))
        self.label.grid(row=row, column=0, sticky="e", padx=(6, 4))

        # Canvas hosts the background + fill rectangle + percent text.
        # The text sits right of the bar (x >= BAR_W) so it never
        # overlaps the fill, even at 100%.
        # Canvas に背景・塗りつぶし・%テキストを描画。テキストはバーの
        # 右側 (x >= BAR_W) に置き、100% でも塗りと重ならないようにする。
        self.canvas = tk.Canvas(parent, width=BAR_W + PCT_W, height=BAR_H,
                                bg=CARD_BG, highlightthickness=0)
        self.canvas.grid(row=row, column=1, sticky="w")
        self.canvas.create_rectangle(0, 0, BAR_W, BAR_H,
                                     fill=BAR_BG, width=0)
        self.rect = self.canvas.create_rectangle(0, 0, 0, BAR_H,
                                                 fill=GOOD, width=0)
        self.txt = self.canvas.create_text(BAR_W + PCT_W, BAR_H // 2,
                                           text="--%", anchor="e",
                                           fill=FG, font=("Helvetica", 10,
                                                           "bold"))

    def set(self, pct):
        """Update the bar width, color, and text for a new percent.
        / 使用率 % が渡されたらバー幅・色・テキストを更新する。"""
        # Clamp to [0, 100] / 値を 0〜100 にクランプ
        pct = max(0.0, min(100.0, pct))
        w = int(BAR_W * pct / 100)
        c = color_for_pct(pct)
        self.canvas.coords(self.rect, 0, 0, w, BAR_H)
        self.canvas.itemconfig(self.rect, fill=c)
        self.canvas.itemconfig(self.txt, text=f"{pct:.0f}%", fill=c)


class GpuCard:
    """A card that displays the information of a single GPU.
    / GPU 1枚分の情報を表示するカード。"""

    def __init__(self, parent, idx, name):
        self.frame = tk.Frame(parent, bg=CARD_BG)
        self.frame.grid(padx=6, pady=3)
        self.frame.columnconfigure(1, weight=1)

        # Title row: "GPU <idx>  <name>" / タイトル行
        tk.Label(self.frame, text=f"GPU {idx}  {name}", anchor="w",
                 bg=CARD_BG, fg=FG,
                 font=("Helvetica", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(5, 0))

        # Three usage bars: GPU / MEM / PWR / 使用率バー 3 本
        self.util_bar = BarWidget(self.frame, 1, "GPU")
        self.util_bar.canvas.grid(pady=(5, 2))
        self.mem_bar = BarWidget(self.frame, 2, "MEM")
        self.mem_bar.canvas.grid(pady=(2, 2))
        self.pwr_bar = BarWidget(self.frame, 3, "PWR")
        self.pwr_bar.canvas.grid(pady=(2, 2))

        # Detail line: MiB / °C / W / 詳細行
        self.detail = tk.Label(self.frame, text="", anchor="w",
                               bg=CARD_BG, fg=DIM, font=("Helvetica", 10))
        self.detail.grid(row=4, column=0, columnspan=2, sticky="ew",
                         padx=6, pady=(0, 5))

    def update(self, g):
        """Push one sample into the card. g is a dict from query_gpus().
        / 1 サンプル分のデータをカードに反映する。
        / g は query_gpus() が返す dict。"""
        self.util_bar.set(g["util"])
        self.mem_bar.set(g["mem_pct"])
        self.pwr_bar.set(g.get("power_pct", 0.0))
        self.detail.config(
            text=f"{g['mem_used']:.0f}/{g['mem_total']:.0f} MiB  "
                 f"{g['temp']:.0f}°C  {g.get('power',0):.0f}/{g.get('power_limit',0):.0f} W")


class App:
    """Main application object.
    / メインアプリケーションクラス。

    Responsibilities (役割):
      - Create the window; manage the always-on-top toggle + persistence.
        / ウィンドウ生成と always-on-top のトグルと永続保存。
      - Create and drive the per-GPU cards via the refresh loop.
        / GPU カードの生成と更新ループ (refresh) の駆動。
      - Initial placement at top-right (_initial_place) and
        content-following fit (_fit) on every refresh.
        / 初期時に右上配置 (_initial_place)、更新毎に内容追従 (_fit)。
      - Update status lines (GPU count and total memory used).
        / 状態行 (GPU 数・総メモリ使用量) の更新。

    refresh() calls query_gpus() every 0.5 s, updates all cards, and
    reschedules itself via root.after().
    / refresh() は 0.5 秒ごとに query_gpus() を呼び出し、カードを更新した
    上で root.after() により再スケジュールする自己再帰関数。
    """
    def __init__(self, always_on_top=None):
        """Build the window and kick off the first refresh.
        / ウィンドウを構築し、最初の refresh を開始する。

        If always_on_top is not given, restore it from the config file;
        the -A CLI flag overrides the saved value.
        / always_on_top が None の場合は設定ファイルから復元する。
          -A フラグは保存値を上書きする。
        """
        if always_on_top is None:
            always_on_top = bool(load_config().get("always_on_top", False))
        self.root = tk.Tk()
        self.root.title("GPU Monitor")
        self.root.configure(bg=BG)
        self.root.minsize(160, 60)
        # Standard close-button behavior / 標準的な閉じボタン動作
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.topmost = bool(always_on_top)
        self.set_topmost(self.topmost)

        # --- Header: title + Always-on-top button / ヘッダー ---
        header = tk.Frame(self.root, bg=BG)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(header, text="GPU Monitor", bg=BG, fg=FG,
                 font=("Helvetica", 12, "bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 0))
        self.top_btn = tk.Button(
            header, text="Always on top",
            activebackground=GOOD, activeforeground=BG,
            relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
            command=self._toggle_topmost)
        self.top_btn.grid(row=0, column=1, sticky="e", padx=10, pady=(8, 0))
        self._update_btn_color()

        # Container for all GPU cards / GPU カードのコンテナ
        self.cards_frame = tk.Frame(self.root, bg=BG)
        self.cards_frame.grid(row=1, column=0, sticky="ew")

        # Status lines (GPU count + total memory used) / 状態表示
        self.status = tk.Label(self.root, text="Loading...",
                               bg=BG, fg=DIM, font=("Helvetica", 10))
        self.status.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 0))
        self.mem_status = tk.Label(self.root, text="", anchor="w",
                                   bg=BG, fg=DIM, font=("Helvetica", 10))
        self.mem_status.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

        self.cards = []
        self._max_req = 0   # Width stabilizer (see _fit) / 幅安定化用
        self._placed = False   # _initial_place done? / 初期配置済みか
        self._last_error = None   # Last error printed to stderr / 直近のエラー
        self.refresh()

    def _toggle_topmost(self):
        """Handle a click on the "Always on top" button.
        / 「Always on top」ボタンのクリックハンドラ。

        Flip the state, refresh the button color, and persist to disk.
        / 状態を反転し、ボタンの色を更新、設定を保存する。
        """
        self.set_topmost(not self.topmost)
        cfg = load_config()
        cfg["always_on_top"] = self.topmost
        save_config(cfg)

    def set_topmost(self, on):
        """Turn the window's always-on-top attribute on/off,
        and keep the button color in sync.
        / ウィンドウの always-on-top を on/off に設定。
          ボタンの色も同期して更新する。
        """
        self.topmost = bool(on)
        self.root.wm_attributes("-topmost", self.topmost)
        self._update_btn_color()

    def _update_btn_color(self):
        """Paint the button green when ON, dim when OFF.
        / ボタンを ON 時 = 緑、OFF 時 = 暗い色で描画。"""
        if not hasattr(self, "top_btn"):
            return
        if self.topmost:
            self.top_btn.config(bg=GOOD, fg=BG)
        else:
            self.top_btn.config(bg=CARD_BG, fg=DIM)

    def _initial_place(self):
        """Place the window at the top-right of the screen the first time.
        / 初回表示時に画面右上に配置する。

        The window size matches the content exactly (no padding).
        / ウィンドウサイズは内容にピッタリ（余白なし）。
        """
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        # Keep at least a minimum of 180 x 60 / 最小 180 x 60 保証
        w = max(self.root.winfo_reqwidth(), 180)
        h = max(self.root.winfo_reqheight(), 60)
        # 20-px inset from the right and top edges / 右・上から 20px 内側
        self.root.geometry(f"{w}x{h}+{sw - w - 20}+20")

    def _fit(self):
        """Resize the window to follow the content on every refresh.
        / 更新毎にウィンドウを内容に追従させる。

        The width is stable: it records the largest ever requested
        width in self._max_req so it never shrinks back. The height
        always follows the current required height.
        / 幅は一度広がったら縮まない (self._max_req に最大幅を保持)。
          高さは毎回必要高さに合わせる。
        """
        req = self.root.winfo_reqwidth()
        if req > self._max_req:
            self._max_req = req
        w = max(self._max_req, 180)
        h = self.root.winfo_reqheight()
        if w != self.root.winfo_width() or h != self.root.winfo_height():
            # Preserve current window position / 現在の位置を保持
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.root.geometry(f"{w}x{h}+{x}+{y}")

    def refresh(self):
        """Fetch the latest data, refresh every card, and reschedule.
        / 最新データを取得しカードを更新、次の更新を予約する。

        The first call creates the cards and places the window at the
        top-right; subsequent calls just update in place.
        / 初回はカード生成とウィンドウ配置、2回目以降は更新のみ。

        On error a short message is shown in the status line (details go
        to stderr once per distinct error) and the loop reschedules
        itself so the app keeps trying to recover.
        / エラー時は短いメッセージを状態行に表示し（詳細は同じエラーに
          つき 1 回だけ stderr へ）、ループを継続して復帰を試みる。
        """
        try:
            gpus = query_gpus()
        except Exception as e:
            detail = f"{e}\n{getattr(e, 'stderr', None) or ''}".strip()
            if detail != self._last_error:
                print(f"gpu_monitor: {detail}", file=sys.stderr)
                self._last_error = detail
            self.status.config(text=f"Error: {short_error(e)}", fg=BAD)
            self.mem_status.config(text="")
            self.root.after(REFRESH_MS, self.refresh)
            return
        self._last_error = None

        if not self.cards:
            # Build one card per detected GPU (retried while none found).
            # 検出された GPU ごとに 1 枚のカード生成（0 枚の間は毎回再試行）。
            for i, g in enumerate(gpus):
                self.cards.append(GpuCard(self.cards_frame, i, g["name"]))
        if not self._placed:
            # Place at the top-right only once, so the user can move the
            # window afterwards even when no GPU is found.
            # 右上への配置は 1 回だけ。GPU が 0 枚でも以後は移動できる。
            self.root.update_idletasks()
            self._initial_place()
            self._placed = True

        # Update each card with fresh numbers / 各カードを最新値で更新
        for card, g in zip(self.cards, gpus):
            card.update(g)

        # Status lines / 状態行
        total_used = sum(g["mem_used"] for g in gpus)
        self.status.config(text=f"{len(self.cards)} GPUs", fg=DIM)
        self.mem_status.config(
            text=f"total memory: {total_used:.0f} MiB used", fg=DIM)

        # Fit the window to the (possibly changed) content.
        # ウィンドウを内容にフィットさせる。
        self.root.update_idletasks()
        self._fit()

        # Schedule the next tick / 次回の更新予約
        self.root.after(REFRESH_MS, self.refresh)


def main():
    """Parse CLI arguments and start the app.
    / コマンドライン引数を解析し App を起動する。

    -A / --always-on-top forces the window to start on top;
    otherwise the saved setting (or default OFF) is used.
    / -A / --always-on-top は常時手前起動を強制。
      そうでなければ設定ファイルの値（未設定時は OFF）を使う。
    """
    p = argparse.ArgumentParser(
        description="NVIDIA GPU usage monitor (small GUI)")
    p.add_argument("--always-on-top", "-A", action="store_true", default=None,
                   help="start with always-on-top "
                        "(default: keep last saved setting)")
    args = p.parse_args()
    App(always_on_top=args.always_on_top).root.mainloop()


if __name__ == "__main__":
    main()
