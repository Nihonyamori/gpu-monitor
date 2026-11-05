#!/usr/bin/env python3
"""
GPU Monitor
=======================
Author    : Takuya Saito
Created   : 2026-11-04

Japanese (概要):
  NVIDIA GPU のリアルタイム使用状況を小さなウィンドウに常時表示する
  tkinter GUI。GPU 使用率・メモリ使用率・消費電力率・温度・メモリ絶対値を
  0.5秒間隔で NVML（使えなければ nvidia-smi）から取得し、カード形式で
  表示する。

English (Summary):
  A tiny tkinter GUI that displays the real-time usage of all NVIDIA
  GPUs in a small window. GPU utilization, memory utilization, power
  draw ratio, temperature and memory size are fetched every 0.5 seconds
  from NVML (or nvidia-smi as a fallback) and rendered as per-GPU cards.

Features (主な機能):
  - 複数 GPU に対応（検出された数だけカード生成）
    / Supports multiple GPUs (one card per detected GPU)
  - 各 GPU につき 3 本の水平バー: GPU / MEM / PWR
    / 3 horizontal bars per GPU: GPU / MEM / PWR
  - 色分け: <70% 緑、70-89% 黄、>=90% 赤
    / Color coding: green < 70%, yellow 70-89%, red >= 90%
  - 詳細行: 使用/総量 MiB, 温度 °C, 電力/上限 W を 1 行表示
    / Detail line: used/total MiB, temperature °C, power/limit W
  - 「Always on top」トグルとウィンドウ位置を ~/.config/gpu_monitor.json
    に保存し、次回起動時に復元する。初回は画面右上に配置。
    / "Always on top" toggle and the window position are persisted to
    ~/.config/gpu_monitor.json and restored on the next launch. The
    first launch places the window at the top-right of the screen.
  - ウィンドウは内容にピッタリフィット（余白 0px）、幅は一度広がった
    ら縮まないよう安定化。
    / Window fits its content exactly (0px padding); width is stable
    (never shrinks).
  - 設定ファイル無くても起動可能（既定値へフォールバック）
    / Works even without a config file (falls back to defaults).
  - 専用アイコン (icon.png) と WM_CLASS "gpu-monitor"。install.sh で
    メニューに登録すると Dock でも同じアイコンと名前になる。
    / Own icon (icon.png) and WM_CLASS "gpu-monitor"; after install.sh
    the dock shows the same icon and name as the menu entry.

Dependencies (依存関係):
  - Python 3 standard library only (tkinter, ctypes, subprocess,
    argparse, json, pathlib, re, signal, sys). No pip packages.
    / Python 3 標準ライブラリのみ（外部パッケージ不要）
  - NVIDIA driver (libnvidia-ml.so.1 or the `nvidia-smi` command).
    / NVIDIA ドライバ（libnvidia-ml.so.1 か `nvidia-smi` コマンド）

Usage (使い方):
  ./gpu_monitor.py                Normal start (restores last settings)
                                  / 通常起動（前回の設定と位置を引き継ぐ）
  ./gpu_monitor.py -A             Start with always-on-top / 常時手前で起動
  ./gpu_monitor.py --no-always-on-top
                                  Start without always-on-top
                                  / 常時手前なしで起動
  ./gpu_monitor.py -R             Start at the top-right, ignoring the
                                  saved position / 保存位置を無視し右上に
  ./gpu_monitor.py --nvidia-smi   Use nvidia-smi instead of NVML
                                  / NVML の代わりに nvidia-smi を使う
  ./gpu_monitor.py --help         Show help / ヘルプ表示

Design notes (設計上のポイント):
  - All logic in one file; no external packages.
    / 全ロジックを1ファイルに集約し、外部パッケージ不要。
  - GPU data comes from a "source" object with query() / close().
    NvmlSource calls libnvidia-ml.so.1 via ctypes (about 2 ms per
    refresh, no process spawn). If NVML cannot be loaded, SmiSource
    runs nvidia-smi (30-40 ms per refresh) with a timeout.
    / GPU データは query() / close() を持つ「ソース」から取る。
      NvmlSource は ctypes で libnvidia-ml.so.1 を直接呼ぶ（1 回約 2ms、
      プロセス起動なし）。NVML を読めなければ SmiSource が nvidia-smi
      を timeout 付きで実行する（1 回 30〜40ms）。
  - UI runs on tkinter's main loop; the source is called synchronously.
    / UI スレッドは tkinter のメインループのみ。ソースは同期で呼ぶ。
  - Window width is stabilized by caching the max requested width in
    self._max_req so it never shrinks back. Initial placement is done
    once by _place_once; subsequent updates are done by _fit.
    / ウィンドウ幅は _max_req に最大必須幅を保持することで縮小しない。
      初期配置は _place_once で 1 回だけ、更新毎に _fit で内容に追随。
  - Persistence is just two small helpers: load_config / save_config.
    / 設定は load_config / save_config の 2 関数で JSON 永続化。
"""
import argparse
import ctypes
import json
import re
import signal
import subprocess
import sys
from pathlib import Path

import tkinter as tk

REFRESH_MS = 500   # Refresh interval in milliseconds / 更新間隔 (ms)
QUERY_TIMEOUT_S = 2  # nvidia-smi timeout in seconds / nvidia-smi のタイムアウト (s)
CONFIG_FILE = Path.home() / ".config" / "gpu_monitor.json"
NVML_LIB = "libnvidia-ml.so.1"   # NVML shared library / NVML の共有ライブラリ
ICON_FILE = Path(__file__).resolve().parent / "icon.png"  # Window icon / ウィンドウアイコン
# X11 WM_CLASS instance name. Must match StartupWMClass in install.sh so
# the dock shows the menu entry's icon and name.
# X11 の WM_CLASS。install.sh の StartupWMClass と一致させると、
# Dock にメニュー項目のアイコンと名前が出る。
WM_CLASS = "gpu-monitor"
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
    を返し、起動を継続させる。Stored keys: always_on_top (bool),
    x / y (int, window position).
    """
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


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


def make_gpu(index, name, temp, util, mem_total, mem_used, power,
             power_limit):
    """Build the per-GPU dict that both data sources return.
    / 両方のデータソースが返す GPU 1 枚分の dict を作る。

    Keys: / キー:
      index                  GPU 番号 / GPU index (same as nvidia-smi)
      name                   GPU 名 / GPU name
      temp                   温度(°C) / Temperature (°C)
      util                   GPU 使用率(%) / GPU utilization (%)
      mem_total / mem_used   メモリ総量/使用量(MiB) / Total/used memory (MiB)
      mem_pct                メモリ使用率(%) / Memory usage (%)
      power / power_limit    消費電力/上限(W) / Power draw / limit (W)
      power_pct              消費電力率(%) / Power draw ratio (%)
    Values a GPU does not report are 0. / GPU が返さない値は 0。
    """
    return dict(
        index=index,
        name=name,
        temp=temp,
        util=util,
        mem_total=mem_total,
        mem_used=mem_used,
        mem_pct=(mem_used / mem_total * 100) if mem_total else 0.0,
        power=power,
        power_limit=power_limit,
        power_pct=(power / power_limit * 100) if power_limit else 0.0,
    )


def query_gpus():
    """Fetch information for all NVIDIA GPUs with nvidia-smi.
    / nvidia-smi で全 GPU の情報を取得する。

    Calls nvidia-smi once and parses a CSV response. Returns a list of
    make_gpu() dicts.
    / nvidia-smi を 1 回呼び出し、CSV で取得する。戻り値は make_gpu()
      の dict の list。

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
        # Power fields (W) - guard for older nvidia-smi / 消費電力 (W)
        power = num(p[6]) if len(p) > 6 else 0.0
        power_lmt = num(p[7]) if len(p) > 7 else 0.0
        gpus.append(make_gpu(
            index=int(num(p[0], len(gpus))),
            name=p[1],
            temp=num(p[2]),
            util=num(p[3]),
            mem_total=num(p[4]),
            mem_used=num(p[5]),
            power=power,
            power_limit=power_lmt,
        ))
    return gpus


class SmiSource:
    """GPU data source that runs the nvidia-smi command (fallback).
    / nvidia-smi コマンドを実行するデータソース（予備）。"""

    name = "nvidia-smi"

    def query(self):
        return query_gpus()

    def close(self):
        pass


# --- NVML (libnvidia-ml) via ctypes ---------------------------------
NVML_SUCCESS = 0
NVML_ERROR_NOT_SUPPORTED = 3
NVML_TEMPERATURE_GPU = 0


class NvmlError(Exception):
    """An NVML call returned an error code. / NVML 呼び出しのエラー。"""


class _NvmlUtilization(ctypes.Structure):    # nvmlUtilization_t
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _NvmlMemory(ctypes.Structure):         # nvmlMemory_t
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                ("used", ctypes.c_ulonglong)]


class _NvmlMemoryV2(ctypes.Structure):       # nvmlMemory_v2_t
    _fields_ = [("version", ctypes.c_uint), ("total", ctypes.c_ulonglong),
                ("reserved", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                ("used", ctypes.c_ulonglong)]


class NvmlSource:
    """GPU data source that calls NVML (libnvidia-ml.so.1) via ctypes.
    / ctypes で NVML (libnvidia-ml.so.1) を直接呼ぶデータソース。

    Raises OSError (library missing) or NvmlError (e.g. driver not
    loaded) on construction; the caller then falls back to SmiSource.
    / ライブラリが無ければ OSError、ドライバ未読み込み等なら NvmlError
      を生成時に送出する。呼び出し側は SmiSource に切り替える。
    """

    name = "NVML"

    def __init__(self):
        self.lib = ctypes.CDLL(NVML_LIB)
        self.lib.nvmlErrorString.restype = ctypes.c_char_p
        self._check(self.lib.nvmlInit_v2())
        # The v2 memory API excludes driver-reserved memory and matches
        # nvidia-smi's memory.used; older drivers only have v1.
        # v2 は予約領域を除いた使用量で nvidia-smi の memory.used と一致
        # する。古いドライバには v1 しかない。
        self._mem_v2 = hasattr(self.lib, "nvmlDeviceGetMemoryInfo_v2")

    def _check(self, ret):
        """Raise NvmlError unless ret is NVML_SUCCESS.
        / ret が成功でなければ NvmlError を送出する。"""
        if ret != NVML_SUCCESS:
            raise NvmlError(self.lib.nvmlErrorString(ret).decode())

    def _uint(self, fn, *args):
        """Call an NVML getter that writes one unsigned int.
        Returns None if the GPU does not support it.
        / unsigned int を 1 つ返す NVML 関数を呼ぶ。非対応なら None。"""
        v = ctypes.c_uint()
        ret = fn(*args, ctypes.byref(v))
        if ret == NVML_ERROR_NOT_SUPPORTED:
            return None
        self._check(ret)
        return v.value

    def _memory(self, h):
        """Return (total, used) memory in bytes. / メモリ総量・使用量 (byte)"""
        if self._mem_v2:
            m = _NvmlMemoryV2(version=ctypes.sizeof(_NvmlMemoryV2) | (2 << 24))
            self._check(self.lib.nvmlDeviceGetMemoryInfo_v2(h, ctypes.byref(m)))
        else:
            m = _NvmlMemory()
            self._check(self.lib.nvmlDeviceGetMemoryInfo(h, ctypes.byref(m)))
        return m.total, m.used

    def query(self):
        """Return a list of make_gpu() dicts, one per GPU.
        / GPU ごとの make_gpu() の dict の list を返す。"""
        lib = self.lib
        count = ctypes.c_uint()
        self._check(lib.nvmlDeviceGetCount_v2(ctypes.byref(count)))
        gpus = []
        for i in range(count.value):
            h = ctypes.c_void_p()
            self._check(lib.nvmlDeviceGetHandleByIndex_v2(i, ctypes.byref(h)))
            name = ctypes.create_string_buffer(96)
            self._check(lib.nvmlDeviceGetName(h, name, len(name)))
            util = _NvmlUtilization()
            ret = lib.nvmlDeviceGetUtilizationRates(h, ctypes.byref(util))
            if ret != NVML_ERROR_NOT_SUPPORTED:
                self._check(ret)
            temp = self._uint(lib.nvmlDeviceGetTemperature, h,
                              NVML_TEMPERATURE_GPU)
            power_mw = self._uint(lib.nvmlDeviceGetPowerUsage, h)
            limit_mw = self._uint(lib.nvmlDeviceGetPowerManagementLimit, h)
            mem_total, mem_used = self._memory(h)
            gpus.append(make_gpu(
                index=i,
                name=name.value.decode(errors="replace"),
                temp=float(temp or 0),
                util=float(util.gpu),
                mem_total=mem_total / 2**20,
                mem_used=mem_used / 2**20,
                power=(power_mw or 0) / 1000,
                power_limit=(limit_mw or 0) / 1000,
            ))
        return gpus

    def close(self):
        self.lib.nvmlShutdown()


def open_source(use_smi=False):
    """Return NvmlSource, or SmiSource if NVML is unavailable or
    use_smi is True.
    / NvmlSource を返す。NVML が使えないか use_smi なら SmiSource。"""
    if not use_smi:
        try:
            return NvmlSource()
        except (OSError, NvmlError) as e:
            print(f"gpu_monitor: NVML unavailable ({e}), using nvidia-smi",
                  file=sys.stderr)
    return SmiSource()


def short_error(e):
    """Return a short one-line message for a data source exception.
    / データソースの例外を、状態行用の短い 1 行メッセージにする。

    str(CalledProcessError) contains the whole argument list (~200
    chars) and would stretch the window, so it is never shown as is.
    / CalledProcessError の文字列は引数一覧を含み約 200 文字になり
      ウィンドウを横に引き伸ばすため、そのままは表示しない。
    """
    if isinstance(e, NvmlError):
        return f"NVML: {e}"
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
        """Push one sample into the card. g is a dict from make_gpu().
        / 1 サンプル分のデータをカードに反映する。
        / g は make_gpu() が作る dict。"""
        self.util_bar.set(g["util"])
        self.mem_bar.set(g["mem_pct"])
        self.pwr_bar.set(g["power_pct"])
        self.detail.config(
            text=f"{g['mem_used']:.0f}/{g['mem_total']:.0f} MiB  "
                 f"{g['temp']:.0f}°C  {g['power']:.0f}/{g['power_limit']:.0f} W")


class App:
    """Main application object.
    / メインアプリケーションクラス。

    Responsibilities (役割):
      - Create the window; manage the always-on-top toggle + persistence.
        / ウィンドウ生成と always-on-top のトグルと永続保存。
      - Create and drive the per-GPU cards via the refresh loop.
        / GPU カードの生成と更新ループ (refresh) の駆動。
      - Initial placement at the saved position or top-right
        (_place_once) and content-following fit (_fit) on every refresh.
        / 初回に保存位置か右上に配置 (_place_once)、更新毎に内容追従 (_fit)。
      - Save the window position and release the source on close.
        / 終了時にウィンドウ位置を保存し、ソースを解放 (close)。
      - Update status lines (GPU count and total memory used).
        / 状態行 (GPU 数・総メモリ使用量) の更新。

    refresh() calls source.query() every 0.5 s, updates all cards, and
    reschedules itself via root.after().
    / refresh() は 0.5 秒ごとに source.query() を呼び出し、カードを更新
    した上で root.after() により再スケジュールする自己再帰関数。
    """
    def __init__(self, source, always_on_top=None, reset_position=False):
        """Build the window and kick off the first refresh.
        / ウィンドウを構築し、最初の refresh を開始する。

        If always_on_top is None, restore it from the config file; the
        -A / --no-always-on-top CLI flags override the saved value.
        The saved window position is used unless reset_position.
        / always_on_top が None の場合は設定ファイルから復元する。
          -A / --no-always-on-top は保存値を上書きする。
          reset_position でなければ保存位置を使う。
        """
        cfg = load_config()
        if always_on_top is None:
            always_on_top = bool(cfg.get("always_on_top", False))
        self.source = source
        self._saved_pos = None if reset_position else (cfg.get("x"),
                                                       cfg.get("y"))
        self.root = tk.Tk(className=WM_CLASS)
        self.root.title("GPU Monitor")
        # Window / dock icon; keep a reference so it is not garbage-collected
        # ウィンドウ・Dock のアイコン。GC されないよう参照を保持する
        try:
            self._icon = tk.PhotoImage(file=str(ICON_FILE))
            self.root.iconphoto(True, self._icon)
        except tk.TclError:
            pass   # icon.png missing: keep the default icon / 無ければ既定のまま
        self.root.configure(bg=BG)
        self.root.minsize(160, 60)
        # Close button saves the position before quitting
        # 閉じるボタンでは位置を保存してから終了
        self.root.protocol("WM_DELETE_WINDOW", self.close)
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
        self._placed = False   # _place_once done? / 初期配置済みか
        self._closed = False   # close() done? / 終了処理済みか
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

    def _place_once(self):
        """Place the window the first time only: at the saved position
        if it is on screen, otherwise at the top-right.
        / 初回だけウィンドウを配置する。保存位置が画面内ならそこに、
          そうでなければ画面右上に置く。

        Placing only once lets the user move the window afterwards,
        even when no GPU is found. The size matches the content exactly.
        / 配置は 1 回だけなので、GPU が 0 枚でも以後は移動できる。
          サイズは内容にピッタリ（余白なし）。
        """
        if self._placed:
            return
        self._placed = True
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        # Keep at least a minimum of 180 x 60 / 最小 180 x 60 保証
        w = max(self.root.winfo_reqwidth(), 180)
        h = max(self.root.winfo_reqheight(), 60)
        # Default: 20-px inset from the right and top edges
        # 既定: 右・上から 20px 内側
        x, y = sw - w - 20, 20
        sx, sy = self._saved_pos or (None, None)
        # Use the saved position only if at least 50 px stay on screen
        # (a monitor may have been removed since).
        # 保存位置は 50px 以上画面内に残る場合だけ使う（モニタを外した等）。
        if (isinstance(sx, int) and isinstance(sy, int)
                and 0 <= sx <= sw - 50 and 0 <= sy <= sh - 50):
            x, y = sx, sy
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _fit(self):
        """Resize the window to follow the content on every refresh.
        / 更新毎にウィンドウを内容に追従させる。

        The width is stable: it records the largest ever requested
        width in self._max_req so it never shrinks back. The height
        always follows the current required height. Only the size is
        set, so the window manager keeps the position.
        / 幅は一度広がったら縮まない (self._max_req に最大幅を保持)。
          高さは毎回必要高さに合わせる。サイズだけ指定するので位置は
          ウィンドウマネージャが保つ。
        """
        req = self.root.winfo_reqwidth()
        if req > self._max_req:
            self._max_req = req
        w = max(self._max_req, 180)
        h = self.root.winfo_reqheight()
        if w != self.root.winfo_width() or h != self.root.winfo_height():
            self.root.geometry(f"{w}x{h}")

    def close(self):
        """Save the window position, release the source, and quit.
        Called by the close button and by SIGINT / SIGTERM.
        / ウィンドウ位置を保存し、ソースを解放して終了する。
          閉じるボタンと SIGINT / SIGTERM から呼ばれる。
        """
        if self._closed:
            return
        self._closed = True
        # wm geometry reports "WxH+X+Y"; X/Y are what geometry() accepts
        # back, so the window reopens at exactly the same place.
        # wm geometry は "WxH+X+Y"。X/Y をそのまま geometry() に渡せば
        # 同じ場所に開く。
        m = re.search(r"\+(-?\d+)\+(-?\d+)$", self.root.geometry())
        if self._placed and m:
            cfg = load_config()
            cfg["x"], cfg["y"] = int(m.group(1)), int(m.group(2))
            save_config(cfg)
        self.source.close()
        self.root.destroy()

    def refresh(self):
        """Fetch the latest data, refresh every card, and reschedule.
        / 最新データを取得しカードを更新、次の更新を予約する。

        The first call creates the cards and places the window;
        subsequent calls just update in place.
        / 初回はカード生成とウィンドウ配置、2回目以降は更新のみ。

        On error a short message is shown in the status line (details go
        to stderr once per distinct error) and the loop reschedules
        itself so the app keeps trying to recover.
        / エラー時は短いメッセージを状態行に表示し（詳細は同じエラーに
          つき 1 回だけ stderr へ）、ループを継続して復帰を試みる。
        """
        try:
            gpus = self.source.query()
        except Exception as e:
            detail = f"{e}\n{getattr(e, 'stderr', None) or ''}".strip()
            if detail != self._last_error:
                print(f"gpu_monitor: {detail}", file=sys.stderr)
                self._last_error = detail
            self.status.config(text=f"Error: {short_error(e)}", fg=BAD)
            self.mem_status.config(text="")
            self._place_once()
            self.root.after(REFRESH_MS, self.refresh)
            return
        self._last_error = None

        if not self.cards:
            # Build one card per detected GPU (retried while none found).
            # 検出された GPU ごとに 1 枚のカード生成（0 枚の間は毎回再試行）。
            for g in gpus:
                self.cards.append(
                    GpuCard(self.cards_frame, g["index"], g["name"]))

        # Update each card with fresh numbers / 各カードを最新値で更新
        for card, g in zip(self.cards, gpus):
            card.update(g)

        # Status lines / 状態行
        n = len(self.cards)
        total_used = sum(g["mem_used"] for g in gpus)
        self.status.config(text=f"{n} GPU" + ("" if n == 1 else "s"), fg=DIM)
        self.mem_status.config(
            text=f"total memory: {total_used:.0f} MiB used", fg=DIM)

        # Place once, then fit the window to the (possibly changed) content.
        # 初回配置のあと、ウィンドウを内容にフィットさせる。
        self._place_once()
        self.root.update_idletasks()
        self._fit()

        # Schedule the next tick / 次回の更新予約
        self.root.after(REFRESH_MS, self.refresh)


def main():
    """Parse CLI arguments and start the app.
    / コマンドライン引数を解析し App を起動する。

    -A / --always-on-top and --no-always-on-top force the initial state;
    otherwise the saved setting (or default OFF) is used.
    / -A / --always-on-top と --no-always-on-top は起動時の状態を強制。
      指定がなければ設定ファイルの値（未設定時は OFF）を使う。
    """
    p = argparse.ArgumentParser(
        description="NVIDIA GPU usage monitor (small GUI)")
    p.add_argument("--always-on-top", "-A", dest="always_on_top",
                   action="store_const", const=True, default=None,
                   help="start with always-on-top "
                        "(default: keep last saved setting)")
    p.add_argument("--no-always-on-top", dest="always_on_top",
                   action="store_const", const=False,
                   help="start without always-on-top")
    p.add_argument("--reset-position", "-R", action="store_true",
                   help="start at the top-right of the screen, "
                        "ignoring the saved window position")
    p.add_argument("--nvidia-smi", action="store_true",
                   help="read GPU data with the nvidia-smi command "
                        "instead of NVML")
    args = p.parse_args()
    app = App(open_source(args.nvidia_smi),
              always_on_top=args.always_on_top,
              reset_position=args.reset_position)
    # Ctrl+C / kill also save the position. The handler only schedules
    # close() so that Tk is touched from the main loop.
    # Ctrl+C / kill でも位置を保存する。ハンドラは close() の予約だけ
    # 行い、Tk の操作はメインループから行う。
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: app._closed or app.root.after(0, app.close))
    app.root.mainloop()


if __name__ == "__main__":
    main()
