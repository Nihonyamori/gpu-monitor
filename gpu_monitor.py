#!/usr/bin/env python3
"""
GPU Monitor
================================================================================
概要:
  NVIDIA GPU のリアルタイム使用状況を小さく右上に常時表示する tkinter GUI。
  GPU 使用率・メモリ使用率・消費電力率・温度・メモリ絶対値を 0.5秒間隔で
  nvidia-smi から取得し、カード形式で表示する。

主な機能:
  - 複数 GPU に対応（検出された数だけカード生成）
  - 各 GPU につき 3 本の水平バー: GPU 利用率 / MEM 利用率 / PWR 利用率
  - 色分け: 90% 以上 = 赤・70% 以上 = 黄・未満 = 緑
  - 詳細行: メモリ使用量/総量 MiB、温度 °C、消費電力/上限 W を 1 行表示
  - 「Always on top」ボタンで常時手前をトグル、状態は ~/.config/gpu_monitor.json
    に永続保存。起動時に前回の状態を復元。
  - ウィンドウは内容にピッタリフィット（余白なし、幅安定化）して画面右上に配置。
  - 設定ファイルが無くても起動可能（静かに既定値へフォールバック）

依存関係:
  - Python 3 標準ライブラリ (tkinter, subprocess, argparse, json, pathlib)
  - NVIDIA ドライバ (nvidia-smi コマンド)

使い方:
  ./gpu_monitor.py                通常起動（前回の always-on-top 状態を引き継ぐ）
  ./gpu_monitor.py -A             常時手前で起動
  ./gpu_monitor.py --help         ヘルプ表示

設計上のポイント:
  - 全ロジックを1ファイルに集約し、外部パッケージ不要。
  - UI スレッドは tkinter のメインループのみ。nvidia-smi は同期 subprocess。
    （0.5s 間隔でも軽量）必要なら threading 化可能。
  - ウィンドウ幅は _max_req を保持して縮小しないよう安定化。
    初期配置は _initial_place、更新毎に _fit で内容に追随。
  - 設定は load_config / save_config の2関数で JSON 永続化。

変更履歴:
  - 2026-11-04: PWR バー追加、詳細行を 1 行に圧縮、Always on top の色反転修正
  - 2026-11-04: ウィンドウ幅 8px 余白 → +0px（内容幅）に調整、幅安定化ロジック導入
"""
import argparse
import json
import subprocess
from pathlib import Path

import tkinter as tk

REFRESH_MS = 500   # refresh interval (ms)
CONFIG_FILE = Path.home() / ".config" / "gpu_monitor.json"
BAR_W = 190        # bar width (px)
BAR_H = 12         # bar height (px)

# --- Colors -------------------------------------------
BG = "#1e1e2e"       # window background
CARD_BG = "#2a2a3c"  # card background
FG = "#e6e6f0"       # normal text
DIM = "#9a9ab0"      # dim text
GOOD = "#4ade80"     # green (<70%)
WARN = "#facc15"     # yellow (70-89%)
BAD = "#f87171"      # red (>=90%)
BAR_BG = "#15151f"   # unused bar area


def load_config():
    """設定ファイル ~/.config/gpu_monitor.json を読み込む。
    存在しない・壊れている場合は空 dict を返し、起動を継続させる。
    保存されるキー例: always_on_top (bool)
    """
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    """設定 dict を ~/.config/gpu_monitor.json に書き込む。
    失敗時は例外を上げずに静かに無視する（ユーザ体験を阻害しない）。
    """
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg))
    except OSError:
        pass


def color_for_pct(pct):
    """使用率パーセントからバー色を返す。
    90% 以 = RED、70% 以上 = YELLOW、それ未満 = GREEN。
    """
    if pct >= 90:
        return BAD
    if pct >= 70:
        return WARN
    return GOOD


def query_gpus():
    """全 GPU の情報取得。

    nvidia-smi を 1 回呼び出し CSV で取得。
    戻り値は dict の list、各要素は次のキーを持つ:
      name: GPU 名
      temp: 温度(°C)
      util: GPU 使用率(%)
      mem_total / mem_used: メモリ総量/使用量(MiB)
      mem_pct: メモリ使用率(%)
      power / power_limit: 消費電力/上限(W)
      power_pct: 消費電力率(%)
    エラー時は呼び出し元で例外を捕捉して状態行に表示する設計。
    """
    out = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,temperature.gpu,utilization.gpu,"
            "memory.total,memory.used,power.draw,power.limit",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    def num(s, default=0.0):
        try:
            return float(s)
        except ValueError:
            return default

    gpus = []
    for line in out.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 6:
            continue
        mem_total, mem_used = num(p[4]), num(p[5])
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


class BarWidget:
    """A single horizontal usage bar with a percentage label."""

    def __init__(self, parent, row, label_text):
        self.label = tk.Label(parent, text=label_text, width=4, anchor="e",
                              bg=CARD_BG, fg=DIM, font=("Helvetica", 10))
        self.label.grid(row=row, column=0, sticky="e", padx=(6, 4))

        self.canvas = tk.Canvas(parent, width=BAR_W, height=BAR_H,
                                bg=CARD_BG, highlightthickness=0)
        self.canvas.grid(row=row, column=1, sticky="w")
        self.canvas.create_rectangle(0, 0, BAR_W, BAR_H,
                                     fill=BAR_BG, width=0)
        self.rect = self.canvas.create_rectangle(0, 0, 0, BAR_H,
                                                 fill=GOOD, width=0)
        self.txt = self.canvas.create_text(BAR_W - 20, BAR_H // 2,
                                           text="--%", anchor="w",
                                           fill=FG, font=("Helvetica", 10,
                                                           "bold"))

    def set(self, pct):
        pct = max(0.0, min(100.0, pct))
        w = int(BAR_W * pct / 100)
        c = color_for_pct(pct)
        self.canvas.coords(self.rect, 0, 0, w, BAR_H)
        self.canvas.itemconfig(self.rect, fill=c)
        self.canvas.itemconfig(self.txt, text=f"{pct:.0f}%", fill=c)


class GpuCard:
    """Card that displays a single GPU."""

    def __init__(self, parent, idx, name):
        self.frame = tk.Frame(parent, bg=CARD_BG)
        self.frame.grid(padx=6, pady=3)
        self.frame.columnconfigure(1, weight=1)

        tk.Label(self.frame, text=f"GPU {idx}  {name}", anchor="w",
                 bg=CARD_BG, fg=FG,
                 font=("Helvetica", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(5, 0))

        self.util_bar = BarWidget(self.frame, 1, "GPU")
        self.util_bar.canvas.grid(pady=(5, 2))
        self.mem_bar = BarWidget(self.frame, 2, "MEM")
        self.mem_bar.canvas.grid(pady=(2, 2))
        self.pwr_bar = BarWidget(self.frame, 3, "PWR")
        self.pwr_bar.canvas.grid(pady=(2, 2))

        self.detail = tk.Label(self.frame, text="", anchor="w",
                               bg=CARD_BG, fg=DIM, font=("Helvetica", 10))
        self.detail.grid(row=4, column=0, columnspan=2, sticky="ew",
                         padx=6, pady=(0, 5))

    def update(self, g):
        self.util_bar.set(g["util"])
        self.mem_bar.set(g["mem_pct"])
        self.pwr_bar.set(g.get("power_pct", 0.0))
        self.detail.config(
            text=f"{g['mem_used']:.0f}/{g['mem_total']:.0f} MiB  "
                 f"{g['temp']:.0f}°C  {g.get('power',0):.0f}/{g.get('power_limit',0):.0f} W")


class App:
    """メインアプリケーション。

    責任:
      - Window 生成と always-on-top の永続化
      - GPU カードの生成/更新ループ (refresh)
      - ウィンドウ配置 (_initial_place) と内容追従 (_fit)
      - 状態行 (GPU 数・総メモリ使用量) の更新

    refresh は 0.5秒ごとに query_gpus() を呼び出し、カードを更新した後
    再スケジュールする自己再帰関数。
    """
    def __init__(self, always_on_top=None):
        """Window を構成し初期 refresh を開始する。設定ファイルから
        always_on_top を復元する (引数で上書き可能)。"""
        if always_on_top is None:
            always_on_top = bool(load_config().get("always_on_top", False))
        self.root = tk.Tk()
        self.root.title("GPU Monitor")
        self.root.configure(bg=BG)
        self.root.minsize(160, 60)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.topmost = always_on_top
        self.set_topmost(self.topmost)

        # Header
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

        self.cards_frame = tk.Frame(self.root, bg=BG)
        self.cards_frame.grid(row=1, column=0, sticky="ew")

        self.status = tk.Label(self.root, text="Loading...",
                               bg=BG, fg=DIM, font=("Helvetica", 10))
        self.status.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 0))
        self.mem_status = tk.Label(self.root, text="", anchor="w",
                                   bg=BG, fg=DIM, font=("Helvetica", 10))
        self.mem_status.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

        self.cards = []
        self._max_req = 0
        self.refresh()

    def _toggle_topmost(self):
        """Always on top ボタンクリック時のハンドラ。
        状態を反転し、色を更新、設定を保存する。"""
        self.set_topmost(not self.topmost)
        cfg = load_config()
        cfg["always_on_top"] = self.topmost
        save_config(cfg)

    def set_topmost(self, on):
        """ウィンドウの always-on-top 属性を on/off する。
        ボタンの色も合わせて更新する。"""
        self.topmost = bool(on)
        self.root.wm_attributes("-topmost", self.topmost)
        self._update_btn_color()

    def _update_btn_color(self):
        """Always on top ボタンの色を現在の topmost 状態に合わせて更新。"""
        if not hasattr(self, "top_btn"):
            return
        if self.topmost:
            self.top_btn.config(bg=GOOD, fg=BG)
        else:
            self.top_btn.config(bg=CARD_BG, fg=DIM)

    def _initial_place(self):
        """初回表示時に画面右上に置く。
        ウィンドウサイズは内容の必要幅・高さに合わせ、余白は無い。"""
        self.root.update_idletasks()
        # Fit width and height exactly to the content (no right/bottom padding).
        sw = self.root.winfo_screenwidth()
        w = max(self.root.winfo_reqwidth(), 180)
        h = max(self.root.winfo_reqheight(), 60)
        self.root.geometry(f"{w}x{h}+{sw - w - 20}+20")

    def _fit(self):
        """更新毎にウィンドウを内容に追従させる。
        幅は一度広がったら縮まない（_max_req）で安定化。余白は無い。
        高さは毎回必要高さに合わせる。"""
        req = self.root.winfo_reqwidth()
        if req > self._max_req:
            self._max_req = req
        w = max(self._max_req, 180)
        h = self.root.winfo_reqheight()
        if w != self.root.winfo_width() or h != self.root.winfo_height():
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.root.geometry(f"{w}x{h}+{x}+{y}")

    def refresh(self):
        """0.5秒ごとに query_gpus() を実行しカードを更新する。
        初回はカードを生成しウィンドウを配置、2回目以降は更新のみ。
        例外時はエラー表示しつつ再スケジュールする。"""
        try:
            gpus = query_gpus()
        except Exception as e:
            self.status.config(text=f"Error: {e}", fg=BAD)
            self.mem_status.config(text="")
            self.root.after(REFRESH_MS, self.refresh)
            return

        # First pass: build cards & position window (top-right)
        if not self.cards:
            for i, g in enumerate(gpus):
                self.cards.append(GpuCard(self.cards_frame, i, g["name"]))
            self.root.update_idletasks()
            self._initial_place()

        for card, g in zip(self.cards, gpus):
            card.update(g)

        total_used = sum(g["mem_used"] for g in gpus)
        self.status.config(text=f"{len(self.cards)} GPUs", fg=DIM)
        self.mem_status.config(
            text=f"total memory: {total_used:.0f} MiB used", fg=DIM)
        self.root.update_idletasks()
        self._fit()
        self.root.after(REFRESH_MS, self.refresh)


def main():
    """コマンドライン引数を解析し App を起動する。
    -A / --always-on-top を指定すると初期状態で常時手前にする。
    未指定時は設定ファイルの値を使用する。"""
    p = argparse.ArgumentParser(
        description="NVIDIA GPU usage monitor (small GUI)")
    p.add_argument("--always-on-top", "-A", action="store_true", default=None,
                   help="start with always-on-top "
                        "(default: keep last saved setting)")
    args = p.parse_args()
    App(always_on_top=args.always_on_top).root.mainloop()


if __name__ == "__main__":
    main()
