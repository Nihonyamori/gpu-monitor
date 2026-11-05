#!/usr/bin/env python3
"""
GPU Monitor
=======================
Author    : Takuya Saito
Created   : 2026-11-04

Japanese (概要):
  NVIDIA GPU のリアルタイム使用状況を小さなウィンドウに常時表示する
  tkinter GUI。GPU 使用率・メモリ使用率・消費電力率・温度・メモリ絶対値を
  0.5秒間隔（変更可）で NVML（使えなければ nvidia-smi）から取得し、カード形式で
  表示する。

English (Summary):
  A tiny tkinter GUI that displays the real-time usage of all NVIDIA
  GPUs in a small window. GPU utilization, memory utilization, power
  draw ratio, temperature and memory size are fetched every 0.5 seconds
  from NVML (or nvidia-smi as a fallback) and rendered as per-GPU cards.

Features (主な機能):
  - 複数 GPU に対応（検出された数だけカード生成、増減したら作り直す）
    / Supports multiple GPUs (one card per GPU, rebuilt when they change)
  - 各 GPU につき 3 本の水平バー: GPU / MEM / PWR
    / 3 horizontal bars per GPU: GPU / MEM / PWR
  - 色分け: <70% 緑、70-89% 黄、>=90% 赤。温度は 80°C 以上で黄、
    90°C 以上で赤。
    / Color coding: green < 70%, yellow 70-89%, red >= 90%; temperature
    turns yellow at 80°C and red at 90°C.
  - 詳細行: 使用/総量 GiB, 温度 °C, 電力/上限 W
    / Detail line: used/total GiB, temperature °C, power/limit W
  - 直近 60 秒の GPU 使用率と温度のグラフ（右クリックメニューで切替）
    / 60-second history graph of GPU utilization and temperature
    (toggled from the right-click menu)
  - カードにマウスを乗せると、その GPU を使っているプロセスを表示
    / Hovering over a card lists the processes using that GPU.
  - メニュー（「⋮」ボタンか右クリック）: 常に手前・コンパクト表示
    （1 GPU 1 行）・グラフ・文字サイズ・更新間隔・不透明度・右上へ移動・
    終了・バージョン
    / Menu ("⋮" button or right-click): always on top, compact view
    (one line per GPU), graph, text size, update interval, opacity,
    move to top-right, quit, version
  - 設定（常に手前・グラフ・コンパクト表示・文字サイズ・更新間隔・
    不透明度・ウィンドウ位置）を
    ~/.config/gpu_monitor.json に保存し、次回起動時に復元する。
    初回は画面右上に配置。
    / Settings (always on top, graph, compact view, text size, update
    interval, opacity, window position) are persisted to ~/.config/gpu_monitor.json and restored
    on the next launch. The first launch places the window at the
    top-right.
  - 二重起動しない（2 つ目は既存のウィンドウを手前に出して終了）
    / Single instance: a second launch brings the existing window to
    the front and exits.
  - ウィンドウは内容にピッタリフィット（余白 0px）、幅は一度広がった
    ら縮まないよう安定化。
    / Window fits its content exactly (0px padding); width is stable
    (never shrinks).
  - 専用アイコン (icon.png) と WM_CLASS "gpu-monitor"。install.sh で
    メニューに登録すると Dock でも同じアイコンと名前になる。
    / Own icon (icon.png) and WM_CLASS "gpu-monitor"; after install.sh
    the dock shows the same icon and name as the menu entry.

Dependencies (依存関係):
  - Python 3 standard library only (tkinter, ctypes, subprocess, socket,
    fcntl, ...). No pip packages.
    / Python 3 標準ライブラリのみ（外部パッケージ不要）
  - NVIDIA driver (libnvidia-ml.so.1 or the `nvidia-smi` command).
    / NVIDIA ドライバ（libnvidia-ml.so.1 か `nvidia-smi` コマンド）

Usage (使い方):
  (installed with pipx: `gpu-monitor` takes the same options
   / pipx で入れた場合は `gpu-monitor` で同じオプション)
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
  ./gpu_monitor.py --new-instance Open another window even if one is
                                  already running / 起動中でも別に開く
  ./gpu_monitor.py --version      Show the version / バージョン表示
  ./gpu_monitor.py --help         Show help / ヘルプ表示

Design notes (設計上のポイント):
  - All logic in one file; no external packages. Tests: tests/.
    / 全ロジックを1ファイルに集約し、外部パッケージ不要。テストは tests/。
  - GPU data comes from a "source" object with query() / processes() /
    close(). NvmlSource calls libnvidia-ml.so.1 via ctypes (about 2 ms
    per refresh, no process spawn). If NVML cannot be loaded, SmiSource
    runs nvidia-smi (30-40 ms per refresh) with a timeout.
    / GPU データは query() / processes() / close() を持つ「ソース」から
      取る。NvmlSource は ctypes で libnvidia-ml.so.1 を直接呼ぶ（1 回
      約 2ms、プロセス起動なし）。NVML を読めなければ SmiSource が
      nvidia-smi を timeout 付きで実行する（1 回 30〜40ms）。
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
import fcntl
import json
import os
import pwd
import re
import signal
import socket
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

import tkinter as tk
import tkinter.font as tkfont

__version__ = "1.1.0"   # Keep in sync with CHANGELOG.md / CHANGELOG.md と揃える

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
TEMP_WARN = 80     # Temperature shown yellow from here (°C) / 黄色になる温度
TEMP_BAD = 90      # Temperature shown red from here (°C) / 赤になる温度
GRAPH_H = 44       # History graph height (px) / 履歴グラフの高さ (px)
LEGEND_H = 12      # Legend strip at the top of the graph (px) / 凡例の帯
GRAPH_SECONDS = 60   # Time span of the graph (s) / グラフの期間 (秒)
# Text size choices: name -> scale of fonts and pixel sizes
# 文字サイズの選択肢: 名前 -> フォントとピクセル寸法の倍率
TEXT_SIZES = {"small": 0.85, "medium": 1.0, "large": 1.3}
UPDATE_INTERVALS_MS = (500, 1000, 2000, 5000)   # Update interval choices / 更新間隔の選択肢
PROC_LIMIT = 15    # Max processes listed in the tooltip / ツールチップの最大行数
GRAPH_MENU_LABEL = "Show history graph (60 s)"
OPACITY_LEVELS = (100, 90, 80, 70, 60)   # Window opacity choices (%) / 不透明度の選択肢

# --- Colors (色) -------------------------------------------
BG = "#1e1e2e"       # Window background / ウィンドウ背景
CARD_BG = "#2a2a3c"  # Card background / カード背景
FG = "#e6e6f0"       # Normal foreground text / 通常テキスト
DIM = "#9a9ab0"      # Dimmed (secondary) text / サブテキスト
GOOD = "#4ade80"     # Green (<70%) / 緑（70%未満）
WARN = "#facc15"     # Yellow (70-89%) / 黄（70-89%）
BAD = "#f87171"      # Red (>=90%) / 赤（90%以上）
BAR_BG = "#15151f"   # Unused bar area / バー未使用エリア
LINE_UTIL = "#60a5fa"  # Graph line: GPU utilization / グラフ線: GPU 使用率
LINE_TEMP = "#fb923c"  # Graph line: temperature / グラフ線: 温度


def load_config():
    """Load the JSON config file.
    / JSON 設定ファイルを読み込む。

    Returns an empty dict if the file does not exist or is corrupted,
    so startup keeps working. / ファイルが無い・壊れている場合は空 dict
    を返し、起動を継続させる。Stored keys: always_on_top (bool),
    show_graph (bool), x / y (int, window position).
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


def update_config(**values):
    """Merge values into the config file. / 設定ファイルに値を書き足す。"""
    cfg = load_config()
    cfg.update(values)
    save_config(cfg)


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


def color_for_temp(temp):
    """Map a temperature (°C) to a text color.
    / 温度 (°C) から文字色を返す。

    >= TEMP_BAD red, >= TEMP_WARN yellow, else dim (normal text).
    / TEMP_BAD 以上 = 赤、TEMP_WARN 以上 = 黄、それ未満 = 通常の薄い色。
    """
    if temp >= TEMP_BAD:
        return BAD
    if temp >= TEMP_WARN:
        return WARN
    return DIM


def fmt_mib(mib):
    """Format a memory size: GiB from 1 GiB up, else MiB.
    / メモリ量を整形する。1 GiB 以上は GiB、未満は MiB。"""
    if mib >= 1024:
        return f"{mib / 1024:.1f} GiB"
    return f"{mib:.0f} MiB"


def fmt_mem_pair(used, total):
    """Format "used/total GiB" (both in MiB). / "使用/総量 GiB" に整形。"""
    return f"{used / 1024:.1f}/{total / 1024:.1f} GiB"


def choose_position(saved, sw, sh, w):
    """Return the (x, y) where the window should first appear.
    / ウィンドウを最初に置く位置 (x, y) を返す。

    saved is (x, y) from the config file (or None). It is used only if
    at least 50 px stay on screen (a monitor may have been removed);
    otherwise the window goes 20 px inside the top-right corner.
    / saved は設定ファイルの (x, y)（無ければ None）。50px 以上画面内に
      残る場合だけ使い（モニタを外した等）、そうでなければ右上から
      20px 内側に置く。
    """
    sx, sy = saved or (None, None)
    if (type(sx) is int and type(sy) is int
            and 0 <= sx <= sw - 50 and 0 <= sy <= sh - 50):
        return sx, sy
    return sw - w - 20, 20


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


def _num(s, default=0.0):
    """Parse a numeric string; return default on failure ("[N/A]" etc.).
    / 数値文字列を float に変換。失敗時（"[N/A]" 等）は default を返す。"""
    try:
        return float(s)
    except ValueError:
        return default


def _run_smi(*args):
    """Run nvidia-smi with args and return its stdout.
    / nvidia-smi を引数付きで実行し、標準出力を返す。

    Exceptions are intentionally let propagate; the caller will catch
    them and show the error. If nvidia-smi does not answer within
    QUERY_TIMEOUT_S, subprocess.TimeoutExpired is raised.
    / 例外は呼び出し元で捕捉して表示する。nvidia-smi が QUERY_TIMEOUT_S
      秒以内に応答しなければ TimeoutExpired を送出する。
    """
    return subprocess.run(
        ["nvidia-smi", *args],
        capture_output=True, text=True, check=True,
        timeout=QUERY_TIMEOUT_S,
    ).stdout.strip()


def query_gpus():
    """Fetch information for all NVIDIA GPUs with nvidia-smi.
    / nvidia-smi で全 GPU の情報を取得する。

    Calls nvidia-smi once and parses a CSV response. Returns a list of
    make_gpu() dicts.
    / nvidia-smi を 1 回呼び出し、CSV で取得する。戻り値は make_gpu()
      の dict の list。
    """
    out = _run_smi(
        "--query-gpu=index,name,temperature.gpu,utilization.gpu,"
        "memory.total,memory.used,power.draw,power.limit",
        "--format=csv,noheader,nounits")
    gpus = []
    for line in out.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 6:
            continue
        # Power fields (W) - guard for older nvidia-smi / 消費電力 (W)
        power = _num(p[6]) if len(p) > 6 else 0.0
        power_lmt = _num(p[7]) if len(p) > 7 else 0.0
        gpus.append(make_gpu(
            index=int(_num(p[0], len(gpus))),
            name=p[1],
            temp=_num(p[2]),
            util=_num(p[3]),
            mem_total=_num(p[4]),
            mem_used=_num(p[5]),
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

    def processes(self, index):
        """Return processes on GPU index (compute only; nvidia-smi does
        not list graphics processes in CSV).
        / GPU index 上のプロセスを返す（nvidia-smi の CSV では compute
          プロセスしか取れない）。

        Each item is {"pid": int, "mem": MiB or None, "kind": "C"}.
        / 各要素は {"pid": int, "mem": MiB か None, "kind": "C"}。
        """
        out = _run_smi("--query-compute-apps=pid,used_memory",
                       "--format=csv,noheader,nounits", "-i", str(index))
        procs = []
        for line in out.splitlines():
            p = [x.strip() for x in line.split(",")]
            if len(p) < 2 or not p[0].isdigit():
                continue
            procs.append({"pid": int(p[0]), "mem": _num(p[1], None),
                          "kind": "C"})
        return procs

    def close(self):
        pass


# --- NVML (libnvidia-ml) via ctypes ---------------------------------
NVML_SUCCESS = 0
NVML_ERROR_NOT_SUPPORTED = 3
NVML_ERROR_INSUFFICIENT_SIZE = 7
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


class _NvmlProcessInfo(ctypes.Structure):    # nvmlProcessInfo_t (for _v3)
    _fields_ = [("pid", ctypes.c_uint), ("usedGpuMemory", ctypes.c_ulonglong),
                ("gpuInstanceId", ctypes.c_uint),
                ("computeInstanceId", ctypes.c_uint)]


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

    def _handle(self, index):
        """Return the device handle of GPU index. / GPU のハンドルを返す。"""
        h = ctypes.c_void_p()
        self._check(self.lib.nvmlDeviceGetHandleByIndex_v2(index,
                                                           ctypes.byref(h)))
        return h

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
            h = self._handle(i)
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

    def _process_list(self, fn, h):
        """Return [(pid, MiB or None)] from one NVML process-list call.
        / NVML のプロセス一覧関数 1 つから [(pid, MiB か None)] を返す。"""
        count = ctypes.c_uint(0)
        ret = fn(h, ctypes.byref(count), None)   # ask for the count first
        if ret == NVML_SUCCESS or ret == NVML_ERROR_NOT_SUPPORTED:
            return []
        if ret != NVML_ERROR_INSUFFICIENT_SIZE:
            self._check(ret)
        size = count.value + 8   # room for processes started meanwhile
        infos = (_NvmlProcessInfo * size)()
        count = ctypes.c_uint(size)
        self._check(fn(h, ctypes.byref(count), infos))
        # usedGpuMemory is ULLONG_MAX when unavailable / 取れない時は最大値
        return [(p.pid, None if p.usedGpuMemory >= 2**63
                 else p.usedGpuMemory / 2**20)
                for p in infos[:count.value]]

    def processes(self, index):
        """Return compute ("C") and graphics ("G") processes on GPU index;
        a process doing both is "C+G". None if the driver lacks the API.
        / GPU index 上の compute ("C")・graphics ("G") プロセスを返す。
          両方なら "C+G"。ドライバに API が無ければ None。

        Each item is {"pid": int, "mem": MiB or None, "kind": str}.
        """
        h = self._handle(index)
        procs = {}
        found_api = False
        for kind, fn_name in (("C", "nvmlDeviceGetComputeRunningProcesses_v3"),
                              ("G", "nvmlDeviceGetGraphicsRunningProcesses_v3")):
            fn = getattr(self.lib, fn_name, None)
            if fn is None:
                continue
            found_api = True
            for pid, mem in self._process_list(fn, h):
                p = procs.setdefault(pid, {"pid": pid, "mem": mem, "kind": ""})
                p["kind"] = f"{p['kind']}+{kind}" if p["kind"] else kind
                if mem is not None:
                    p["mem"] = max(p["mem"] or 0, mem)
        return list(procs.values()) if found_api else None

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


def describe_pid(pid):
    """Return (user, command line) of a process from /proc.
    ("?", "?") if it is not visible (ended, or in another container).
    / /proc からプロセスの (ユーザ名, コマンドライン) を返す。見えない
      （終了済み・別コンテナ）なら ("?", "?")。"""
    proc = Path(f"/proc/{pid}")
    try:
        uid = proc.stat().st_uid
        args = [a.decode(errors="replace")
                for a in (proc / "cmdline").read_bytes().split(b"\0") if a]
        comm = (proc / "comm").read_text().strip()
    except OSError:
        return "?", "?"
    try:
        user = pwd.getpwuid(uid).pw_name
    except KeyError:
        user = str(uid)
    name = " ".join([os.path.basename(args[0])] + args[1:]) if args else comm
    return user, name


def format_processes(procs, limit=PROC_LIMIT):
    """Format a processes() result as a fixed-width table, largest
    memory first.
    / processes() の結果を、メモリの大きい順に固定幅の表にする。"""
    if procs is None:
        return "Process list not available"
    if not procs:
        return "No processes"
    rows = sorted(procs, key=lambda p: -1 if p["mem"] is None else p["mem"],
                  reverse=True)
    lines = [f"{'PID':>7}  {'USER':<10} {'MEM':>9}  {'TYPE':<4} COMMAND"]
    for p in rows[:limit]:
        user, name = describe_pid(p["pid"])
        mem = "?" if p["mem"] is None else fmt_mib(p["mem"])
        if len(name) > 40:
            name = name[:37] + "..."
        lines.append(f"{p['pid']:>7}  {user[:10]:<10} {mem:>9}  "
                     f"{p['kind']:<4} {name}")
    if len(rows) > limit:
        lines.append(f"... {len(rows) - limit} more")
    lines.append("C = compute, G = graphics")
    return "\n".join(lines)


class SingleInstance:
    """Keep only one window per user and display.
    / ユーザ・ディスプレイごとにウィンドウを 1 つに保つ。

    The first instance holds an flock on a lock file and listens on a
    UNIX socket next to it. A later instance fails to get the lock,
    connects to the socket so the first window comes to the front, and
    exits. The lock is released by the OS even if the process is
    killed, so a stale lock never blocks startup.
    / 1 つ目はロックファイルを flock し、隣の UNIX ソケットで待ち受ける。
      2 つ目はロックを取れないのでソケットに接続して 1 つ目を手前に出させ、
      自分は終了する。flock は強制終了時も OS が解放するので、古いロック
      で起動できなくなることはない。
    """

    def __init__(self, run_dir=None):
        run_dir = run_dir or os.environ.get("XDG_RUNTIME_DIR") \
            or tempfile.gettempdir()
        display = re.sub(r"[^\w.-]", "_", os.environ.get("DISPLAY", ""))
        base = f"{run_dir}/gpu-monitor-{os.getuid()}-{display}"
        self.lock_path = Path(base + ".lock")
        self.sock_path = Path(base + ".sock")
        self._lock = None
        self.server = None

    def acquire(self):
        """Return True if this is the first instance (now listening).
        Otherwise ask the first one to come to the front and return False.
        / 1 つ目なら True（待ち受け開始）。そうでなければ 1 つ目に手前に
          出るよう頼んで False。"""
        try:
            self._lock = open(self.lock_path, "w")
        except OSError:
            return True   # cannot create the lock: do not block startup
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock.close()
            self._lock = None
            try:
                with socket.socket(socket.AF_UNIX) as s:
                    s.settimeout(1)
                    s.connect(str(self.sock_path))
                    s.sendall(b"raise\n")
            except OSError:
                pass   # the first instance is still starting
            return False
        try:
            self.sock_path.unlink()
        except FileNotFoundError:
            pass
        try:
            self.server = socket.socket(socket.AF_UNIX)
            self.server.bind(str(self.sock_path))
            self.server.listen(4)
            self.server.setblocking(False)
        except OSError:
            self.server = None   # still single-instance via the lock
        return True

    def attach(self, root, on_request):
        """Call on_request() from the Tk main loop when another instance
        connects. / 他のインスタンスが接続したら on_request() を呼ぶ。"""
        if self.server is None:
            return

        def handle(*_):
            try:
                conn, _ = self.server.accept()
                conn.close()
            except OSError:
                return
            on_request()
        root.tk.createfilehandler(self.server, tk.READABLE, handle)

    def close(self):
        if self.server is not None:
            self.server.close()
            self.server = None
            try:
                self.sock_path.unlink()
            except FileNotFoundError:
                pass
        if self._lock is not None:
            self._lock.close()   # releases the flock
            self._lock = None


class Style:
    """Fonts and pixel sizes for the current text size.
    / 現在の文字サイズのフォントとピクセル寸法。

    The fonts are Tk named fonts, so set_size() updates every widget
    that uses them at once. Pixel sizes (bars, graph) are read when a
    widget is built, so the cards are rebuilt after a size change.
    / フォントは Tk の名前付きフォントなので、set_size() で使っている
      ウィジェットがすべて一度に変わる。バーやグラフのピクセル寸法は
      作成時に読むので、サイズ変更後はカードを作り直す。
    """

    def __init__(self, root, text_size="medium"):
        self.normal = tkfont.Font(root, family="Helvetica", size=10)
        self.bold = tkfont.Font(root, family="Helvetica", size=10,
                                weight="bold")
        self.title = tkfont.Font(root, family="Helvetica", size=12,
                                 weight="bold")
        self.small = tkfont.Font(root, family="Helvetica", size=8)
        self.mono = tkfont.nametofont("TkFixedFont").copy()
        self._mono_size = self.mono.cget("size")
        self.set_size(text_size)

    def set_size(self, text_size):
        """Apply one of TEXT_SIZES (unknown names mean "medium").
        / TEXT_SIZES のどれかを適用する（不明なら "medium"）。"""
        self.text_size = text_size if text_size in TEXT_SIZES else "medium"
        self.scale = TEXT_SIZES[self.text_size]
        for font, base in ((self.normal, 10), (self.bold, 10),
                           (self.title, 12), (self.small, 8),
                           (self.mono, self._mono_size)):
            # Negative sizes are pixels in Tk; keep the sign
            # Tk では負のサイズはピクセル指定なので符号を保つ
            size = round(base * self.scale)
            font.configure(size=size if size != 0 else base)

    def px(self, n):
        """Scale a pixel size. / ピクセル寸法を倍率に合わせる。"""
        return max(1, round(n * self.scale))

    @property
    def pct_w(self):
        """Width of the "100%" text right of a bar. / バー右の % 欄の幅"""
        return self.bold.measure("100%") + self.px(4)


class BarWidget:
    """A single horizontal usage bar with a percentage label.
    / パーセンテージラベル付きの水平バー1本。"""

    def __init__(self, parent, row, label_text, style):
        # Left-side label (GPU / MEM / PWR) / 左端のラベル
        self.label = tk.Label(parent, text=label_text, width=4, anchor="e",
                              bg=CARD_BG, fg=DIM, font=style.normal)
        self.label.grid(row=row, column=0, sticky="e", padx=(6, 4))

        # Canvas hosts the background + fill rectangle + percent text.
        # The text sits right of the bar (x >= bar_w) so it never
        # overlaps the fill, even at 100%.
        # Canvas に背景・塗りつぶし・%テキストを描画。テキストはバーの
        # 右側 (x >= bar_w) に置き、100% でも塗りと重ならないようにする。
        self.bar_w, self.bar_h = style.px(BAR_W), style.px(BAR_H)
        width = self.bar_w + style.pct_w
        self.canvas = tk.Canvas(parent, width=width, height=self.bar_h,
                                bg=CARD_BG, highlightthickness=0)
        self.canvas.grid(row=row, column=1, sticky="w")
        self.canvas.create_rectangle(0, 0, self.bar_w, self.bar_h,
                                     fill=BAR_BG, width=0)
        self.rect = self.canvas.create_rectangle(0, 0, 0, self.bar_h,
                                                 fill=GOOD, width=0)
        self.txt = self.canvas.create_text(width, self.bar_h // 2,
                                           text="--%", anchor="e",
                                           fill=FG, font=style.bold)

    def set(self, pct):
        """Update the bar width, color, and text for a new percent.
        / 使用率 % が渡されたらバー幅・色・テキストを更新する。"""
        # Clamp to [0, 100] / 値を 0〜100 にクランプ
        pct = max(0.0, min(100.0, pct))
        w = int(self.bar_w * pct / 100)
        c = color_for_pct(pct)
        self.canvas.coords(self.rect, 0, 0, w, self.bar_h)
        self.canvas.itemconfig(self.rect, fill=c)
        self.canvas.itemconfig(self.txt, text=f"{pct:.0f}%", fill=c)


class History:
    """The last GRAPH_SECONDS of GPU utilization and temperature of one
    GPU. Kept by App per GPU, so it survives card rebuilds (text size,
    compact view) and hidden graphs.
    / GPU 1 枚の直近 GRAPH_SECONDS 秒の使用率と温度。App が GPU ごとに
      持つので、カードの作り直し（文字サイズ・コンパクト表示）やグラフ
      非表示の間も消えない。
    """

    def __init__(self, points):
        self.util = deque(maxlen=points)
        self.temp = deque(maxlen=points)

    @property
    def points(self):
        return self.util.maxlen

    def add(self, util, temp):
        self.util.append(max(0.0, min(100.0, util)))
        self.temp.append(max(0.0, min(100.0, temp)))

    def resize(self, points):
        """Change the number of points, keeping the newest samples.
        / 点数を変える（新しいサンプルを残す）。"""
        self.util = deque(self.util, maxlen=points)
        self.temp = deque(self.temp, maxlen=points)


class HistoryGraph:
    """A small line graph of a History: GPU utilization (%) and
    temperature (°C), both on a 0-100 scale, newest at the right.
    / History の小さな折れ線グラフ。GPU 使用率 (%) と温度 (°C) を
      どちらも 0〜100 の目盛りで、最新を右端に描く。
    """

    def __init__(self, parent, row, style):
        self.style = style
        self.history = None
        self.height = style.px(GRAPH_H)
        # Width 1 + sticky "ew": the canvas takes the card's width
        # 幅 1 + sticky "ew" でカードの幅いっぱいに広がる
        self.canvas = tk.Canvas(parent, width=1, height=self.height,
                                bg=BAR_BG, highlightthickness=0)
        self.canvas.grid(row=row, column=0, columnspan=2, sticky="ew",
                         padx=6, pady=(0, 6))
        self.canvas.bind("<Configure>", lambda e: self.draw())

    def show(self, history):
        self.history = history
        if self.canvas.winfo_ismapped():
            self.draw()

    def set_visible(self, on):
        if on:
            self.canvas.grid()
        else:
            self.canvas.grid_remove()

    def draw(self):
        c, st, hist = self.canvas, self.style, self.history
        w, h = c.winfo_width(), self.height
        if w <= 1 or hist is None:
            return
        c.delete("all")
        # Plot area below the legend strip / 凡例の帯の下が描画領域
        top, bottom = st.px(LEGEND_H) + 3, h - 2
        y_of = lambda v: bottom - v / 100 * (bottom - top)  # noqa: E731
        # 50 % / 50 °C guide line / 50 の目安線
        c.create_line(0, y_of(50), w, y_of(50), fill=CARD_BG)
        step = (w - 1) / max(1, hist.points - 1)
        for values, color in ((hist.temp, LINE_TEMP), (hist.util, LINE_UTIL)):
            if len(values) < 2:
                continue
            # Newest sample at the right edge / 最新の値を右端に
            x0 = (w - 1) - (len(values) - 1) * step
            pts = []
            for i, v in enumerate(values):
                pts += [x0 + i * step, y_of(v)]
            c.create_line(*pts, fill=color, width=1.5)
        legend_x = 4 + st.small.measure("GPU %") + st.px(10)
        c.create_text(4, 1, text="GPU %", anchor="nw", fill=LINE_UTIL,
                      font=st.small)
        c.create_text(legend_x, 1, text="Temp °C", anchor="nw",
                      fill=LINE_TEMP, font=st.small)
        c.create_text(w - 4, 1, text=f"last {GRAPH_SECONDS} s", anchor="ne",
                      fill=DIM, font=st.small)


def pointer_inside(widget):
    """True if the mouse pointer is inside widget.
    / マウスポインタが widget の中にあれば True。"""
    px, py = widget.winfo_pointerxy()
    x, y = widget.winfo_rootx(), widget.winfo_rooty()
    return (x <= px < x + widget.winfo_width()
            and y <= py < y + widget.winfo_height())


class GpuCard:
    """A card that displays the information of a single GPU.
    / GPU 1枚分の情報を表示するカード。"""

    def __init__(self, parent, idx, name, style, show_graph=True):
        self.index = idx
        self.name = name
        self.frame = tk.Frame(parent, bg=CARD_BG)
        self.frame.grid(padx=6, pady=3)
        self.frame.columnconfigure(1, weight=1)

        # Title row: "GPU <idx>  <name>" / タイトル行
        tk.Label(self.frame, text=f"GPU {idx}  {name}", anchor="w",
                 bg=CARD_BG, fg=FG, font=style.bold).grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(5, 0))

        # Three usage bars: GPU / MEM / PWR / 使用率バー 3 本
        self.util_bar = BarWidget(self.frame, 1, "GPU", style)
        self.util_bar.canvas.grid(pady=(5, 2))
        self.mem_bar = BarWidget(self.frame, 2, "MEM", style)
        self.mem_bar.canvas.grid(pady=(2, 2))
        self.pwr_bar = BarWidget(self.frame, 3, "PWR", style)
        self.pwr_bar.canvas.grid(pady=(2, 2))

        # Detail line: GiB / °C / W as separate labels so that only the
        # temperature can change color.
        # 詳細行: 温度だけ色を変えられるよう GiB / °C / W を別ラベルにする
        detail = tk.Frame(self.frame, bg=CARD_BG)
        detail.grid(row=4, column=0, columnspan=2, sticky="ew",
                    padx=6, pady=(0, 4))
        self.mem_lbl = tk.Label(detail, bg=CARD_BG, fg=DIM, font=style.normal)
        self.temp_lbl = tk.Label(detail, bg=CARD_BG, fg=DIM, font=style.normal)
        self.pwr_lbl = tk.Label(detail, bg=CARD_BG, fg=DIM, font=style.normal)
        for lbl in (self.mem_lbl, self.temp_lbl, self.pwr_lbl):
            lbl.pack(side="left", padx=(0, 10))

        self.graph = HistoryGraph(self.frame, 5, style)
        self.graph.set_visible(show_graph)

    def update(self, g, history=None):
        """Push one sample into the card. g is a dict from make_gpu();
        history is this GPU's History for the graph.
        / 1 サンプル分のデータをカードに反映する。g は make_gpu() の
          dict、history はグラフ用のこの GPU の History。"""
        self.util_bar.set(g["util"])
        self.mem_bar.set(g["mem_pct"])
        self.pwr_bar.set(g["power_pct"])
        self.mem_lbl.config(text=fmt_mem_pair(g["mem_used"], g["mem_total"]))
        self.temp_lbl.config(text=f"{g['temp']:.0f}°C",
                             fg=color_for_temp(g["temp"]))
        self.pwr_lbl.config(
            text=f"{g['power']:.0f}/{g['power_limit']:.0f} W")
        if history is not None:
            self.graph.show(history)

    def set_graph_visible(self, on):
        self.graph.set_visible(on)


class CompactRow:
    """One-line view of a GPU for compact mode:
    "GPU 0  G 12%  M 9%  P 9%  51°C" (GPU / memory / power %, temperature).
    Same interface as GpuCard (index, name, frame, update,
    set_graph_visible).
    / コンパクト表示の 1 行: "GPU 0  G 12%  M 9%  P 9%  51°C"（GPU・
      メモリ・電力の %、温度）。GpuCard と同じインタフェース。
    """

    def __init__(self, parent, idx, name, style):
        self.index = idx
        self.name = name
        self.frame = tk.Frame(parent, bg=CARD_BG)
        self.frame.grid(padx=6, pady=2, sticky="ew")
        tk.Label(self.frame, text=f"GPU {idx}", bg=CARD_BG, fg=FG,
                 font=style.bold).pack(side="left", padx=(6, 6), pady=3)
        self.pct_lbls = {}
        for key, short in (("util", "G"), ("mem_pct", "M"),
                           ("power_pct", "P")):
            tk.Label(self.frame, text=short, bg=CARD_BG, fg=DIM,
                     font=style.normal).pack(side="left")
            lbl = tk.Label(self.frame, text="--%", width=4, anchor="e",
                           bg=CARD_BG, fg=FG, font=style.bold)
            lbl.pack(side="left", padx=(0, 6))
            self.pct_lbls[key] = lbl
        self.temp_lbl = tk.Label(self.frame, text="--°C", width=5, anchor="e",
                                 bg=CARD_BG, fg=DIM, font=style.normal)
        self.temp_lbl.pack(side="left", padx=(0, 6))

    def update(self, g, history=None):
        for key, lbl in self.pct_lbls.items():
            pct = max(0.0, min(100.0, g[key]))
            lbl.config(text=f"{pct:.0f}%", fg=color_for_pct(pct))
        self.temp_lbl.config(text=f"{g['temp']:.0f}°C",
                             fg=color_for_temp(g["temp"]))

    def set_graph_visible(self, on):
        pass   # no graph in compact mode / コンパクト表示にグラフは無い


class Tooltip:
    """A borderless popup shown next to a widget (process list).
    / ウィジェットの横に出す枠なしのポップアップ（プロセス一覧用）。"""

    def __init__(self, root, style):
        self.root = root
        self.style = style
        self.win = None
        self.owner = None   # Card the tooltip belongs to / 表示中のカード

    def show(self, owner, widget, text):
        """Show text left of widget (or right if there is no room).
        / widget の左（入らなければ右）に text を表示する。"""
        if self.win is None:
            self.win = tk.Toplevel(self.root, bg=DIM)
            self.win.overrideredirect(True)
            self.win.attributes("-topmost", True)
            self.label = tk.Label(self.win, justify="left", bg=BAR_BG, fg=FG,
                                  font=self.style.mono, padx=8, pady=6)
            self.label.pack(padx=1, pady=1)   # 1px DIM border / 枠線
        self.owner = owner
        self.label.config(text=text)
        self.win.update_idletasks()
        tw = self.win.winfo_reqwidth()
        x = widget.winfo_rootx() - tw - 8
        if x < 0:
            x = widget.winfo_rootx() + widget.winfo_width() + 8
        self.win.geometry(f"+{x}+{widget.winfo_rooty()}")

    def hide(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None
        self.owner = None


class App:
    """Main application object.
    / メインアプリケーションクラス。

    Responsibilities (役割):
      - Create the window; manage always-on-top / graph settings and the
        right-click menu. / ウィンドウ生成、常に手前・グラフ設定と
        右クリックメニュー。
      - Create and drive the per-GPU cards via the refresh loop; rebuild
        them when the set of GPUs changes.
        / GPU カードの生成と更新ループ (refresh) の駆動。GPU の構成が
          変わったらカードを作り直す。
      - Show the process list when the mouse is over a card.
        / カードにマウスが乗ったらプロセス一覧を表示。
      - Initial placement at the saved position or top-right
        (_place_once) and content-following fit (_fit) on every refresh.
        / 初回に保存位置か右上に配置 (_place_once)、更新毎に内容追従 (_fit)。
      - Save the window position and release the source on close.
        / 終了時にウィンドウ位置を保存し、ソースを解放 (close)。

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
        self.topmost_var = tk.BooleanVar(value=bool(always_on_top))
        self.graph_var = tk.BooleanVar(value=bool(cfg.get("show_graph", True)))
        self.compact_var = tk.BooleanVar(value=bool(cfg.get("compact", False)))
        opacity = cfg.get("opacity", 100)
        self.opacity_var = tk.IntVar(
            value=opacity if opacity in OPACITY_LEVELS else 100)
        self.root.wm_attributes("-alpha", self.opacity_var.get() / 100)
        self.style = Style(self.root, cfg.get("text_size", "medium"))
        self.text_size_var = tk.StringVar(value=self.style.text_size)
        interval = cfg.get("interval_ms", REFRESH_MS)
        self.interval_var = tk.IntVar(
            value=interval if interval in UPDATE_INTERVALS_MS else REFRESH_MS)

        # --- Header: title + Always-on-top button / ヘッダー ---
        header = tk.Frame(self.root, bg=BG)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="GPU Monitor", bg=BG, fg=FG,
                 font=self.style.title).grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 0))
        self.top_btn = tk.Button(
            header, text="Always on top",
            activebackground=GOOD, activeforeground=BG,
            relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
            font=self.style.normal,
            command=lambda: self._save_topmost(not self.topmost))
        self.top_btn.grid(row=0, column=1, sticky="e", padx=(10, 2),
                          pady=(8, 0))
        # "⋮" opens the same menu as a right-click
        # 「⋮」で右クリックと同じメニューを開く
        self.menu_btn = tk.Button(
            header, text="⋮", bg=BG, fg=DIM, activebackground=CARD_BG,
            activeforeground=FG, relief="flat", bd=0, padx=6, pady=0,
            cursor="hand2", font=self.style.title,
            command=self._popup_menu_at_button)
        self.menu_btn.grid(row=0, column=2, sticky="e", padx=(0, 4),
                           pady=(8, 0))
        self.set_topmost(always_on_top)

        # Container for all GPU cards / GPU カードのコンテナ
        self.cards_frame = tk.Frame(self.root, bg=BG)
        self.cards_frame.grid(row=1, column=0, sticky="ew")

        # Status lines (GPU count + total memory used) / 状態表示
        self.status = tk.Label(self.root, text="Loading...",
                               bg=BG, fg=DIM, font=self.style.normal)
        self.status.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 0))
        self.mem_status = tk.Label(self.root, text="", anchor="w",
                                   bg=BG, fg=DIM, font=self.style.normal)
        self.mem_status.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))

        # Menu (right-click or "⋮") / メニュー（右クリックか「⋮」）
        def new_menu(parent):
            return tk.Menu(parent, tearoff=0, bg=CARD_BG, fg=FG,
                           activebackground=BAR_BG, activeforeground=FG,
                           selectcolor=GOOD, bd=0, font=self.style.normal)
        self.menu = new_menu(self.root)
        self.menu.add_checkbutton(
            label="Always on top", variable=self.topmost_var,
            command=lambda: self._save_topmost(self.topmost_var.get()))
        self.menu.add_checkbutton(
            label="Compact view", variable=self.compact_var,
            command=self._toggle_compact)
        self.menu.add_checkbutton(
            label=GRAPH_MENU_LABEL, variable=self.graph_var,
            command=self._toggle_graph)
        size_menu = new_menu(self.menu)
        for name in TEXT_SIZES:
            size_menu.add_radiobutton(
                label=name.capitalize(), value=name,
                variable=self.text_size_var, command=self._set_text_size)
        self.menu.add_cascade(label="Text size", menu=size_menu)
        interval_menu = new_menu(self.menu)
        for ms in UPDATE_INTERVALS_MS:
            interval_menu.add_radiobutton(
                label=f"{ms / 1000:g} s", value=ms,
                variable=self.interval_var, command=self._set_interval)
        self.menu.add_cascade(label="Update interval", menu=interval_menu)
        opacity_menu = new_menu(self.menu)
        for level in OPACITY_LEVELS:
            opacity_menu.add_radiobutton(
                label=f"{level}%", value=level, variable=self.opacity_var,
                command=self._set_opacity)
        self.menu.add_cascade(label="Opacity", menu=opacity_menu)
        self.menu.add_separator()
        self.menu.add_command(label="Move to top-right",
                              command=self._move_top_right)
        self.menu.add_command(label="Quit", command=self.close)
        self.menu.add_separator()
        self.menu.add_command(label=f"GPU Monitor {__version__}",
                              state="disabled")
        self.root.bind("<Button-3>", self._popup_menu)

        self.tooltip = Tooltip(self.root, self.style)
        self.cards = []
        # Graph history per GPU (index, name); survives card rebuilds
        # GPU (index, name) ごとのグラフ履歴。カードを作り直しても残る
        self.history = {}
        self._card_keys = []   # [(index, name)] of the cards / カードの構成
        self._max_req = 0   # Width stabilizer (see _fit) / 幅安定化用
        self._placed = False   # _place_once done? / 初期配置済みか
        self._closed = False   # close() done? / 終了処理済みか
        self._last_error = None   # Last error printed to stderr / 直近のエラー
        self._after_id = None   # Next refresh() timer / 次の refresh の予約
        self._last_gpus = []   # Latest query() result / 直近の取得結果
        self._apply_compact_layout()
        self.refresh()

    # --- Settings / 設定 -------------------------------------------
    def set_topmost(self, on):
        """Turn the window's always-on-top attribute on/off, and keep
        the button color and menu check in sync.
        / ウィンドウの always-on-top を on/off に設定。ボタンの色と
          メニューのチェックも同期する。
        """
        self.topmost = bool(on)
        self.topmost_var.set(self.topmost)
        self.root.wm_attributes("-topmost", self.topmost)
        if self.topmost:
            self.top_btn.config(bg=GOOD, fg=BG)
        else:
            self.top_btn.config(bg=CARD_BG, fg=DIM)

    def _save_topmost(self, on):
        """Button / menu handler: set always-on-top and persist it.
        / ボタン・メニューから: 常に手前を設定して保存する。"""
        self.set_topmost(on)
        update_config(always_on_top=self.topmost)

    def _toggle_graph(self):
        """Menu handler: show/hide the history graphs and persist it.
        / メニューから: 履歴グラフの表示を切り替えて保存する。"""
        on = self.graph_var.get()
        for card in self.cards:
            card.set_graph_visible(on)
        update_config(show_graph=on)
        self.root.update_idletasks()
        self._fit()

    def _toggle_compact(self):
        """Menu handler: switch between cards and one-line rows, and
        persist it. The width may shrink once after switching.
        / メニューから: カードと 1 行表示を切り替えて保存する。切替直後は
          幅が縮むのを許す。"""
        update_config(compact=self.compact_var.get())
        self._apply_compact_layout()
        self._relayout()

    def _set_text_size(self):
        """Menu handler: change the text size and persist it. Fonts
        follow at once; cards are rebuilt for the new pixel sizes.
        / メニューから: 文字サイズを変えて保存する。フォントはすぐ追従し、
          カードは新しいピクセル寸法で作り直す。"""
        self.style.set_size(self.text_size_var.get())
        update_config(text_size=self.style.text_size)
        self._relayout()

    def _set_interval(self):
        """Menu handler: change the update interval and persist it. The
        graphs keep covering GRAPH_SECONDS, so their point count changes.
        / メニューから: 更新間隔を変えて保存する。グラフは常に
          GRAPH_SECONDS 秒分なので、点数を変える。"""
        update_config(interval_ms=self.interval_var.get())
        for hist in self.history.values():
            hist.resize(self.graph_points)
        self.refresh()   # reschedules with the new interval / 新しい間隔で再予約

    @property
    def graph_points(self):
        """Samples in GRAPH_SECONDS at the current interval.
        / 現在の更新間隔で GRAPH_SECONDS 秒分の点数。"""
        return max(2, GRAPH_SECONDS * 1000 // self.interval_var.get())

    def _relayout(self):
        """Rebuild the cards with the latest values, letting the width
        shrink once (after a mode or text size change).
        / 直近の値でカードを作り直し、1 回だけ幅が縮むのを許す
          （表示モードや文字サイズの変更後）。"""
        self._rebuild_cards(self._last_gpus)
        self._update_cards(self._last_gpus)
        self._max_req = 0
        self.root.update_idletasks()
        self._fit()

    def _apply_compact_layout(self):
        """Compact mode hides the total-memory line and disables the
        graph menu item. / コンパクト表示ではメモリ合計の行を隠し、
        グラフのメニュー項目を無効にする。"""
        compact = self.compact_var.get()
        if compact:
            self.mem_status.grid_remove()
        else:
            self.mem_status.grid()
        self.menu.entryconfigure(GRAPH_MENU_LABEL,
                                 state="disabled" if compact else "normal")

    def _set_opacity(self):
        """Menu handler: apply and persist the window opacity.
        / メニューから: ウィンドウの不透明度を反映して保存する。"""
        level = self.opacity_var.get()
        self.root.wm_attributes("-alpha", level / 100)
        update_config(opacity=level)

    def _popup_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _popup_menu_at_button(self):
        b = self.menu_btn
        try:
            self.menu.tk_popup(b.winfo_rootx(),
                               b.winfo_rooty() + b.winfo_height())
        finally:
            self.menu.grab_release()

    def bring_to_front(self):
        """Raise the window (another instance was started).
        / ウィンドウを手前に出す（2 つ目が起動された時）。"""
        self.root.deiconify()
        self.root.lift()
        # Briefly force topmost so the window manager really raises it
        # 一時的に topmost にして確実に前面へ出す
        self.root.wm_attributes("-topmost", True)
        self.root.after(300, lambda: self.root.wm_attributes(
            "-topmost", self.topmost))
        self.root.focus_force()

    # --- Window placement / ウィンドウ配置 ---------------------------
    def _place_once(self):
        """Place the window the first time only (see choose_position).
        / 初回だけウィンドウを配置する（choose_position 参照）。

        Placing only once lets the user move the window afterwards,
        even when no GPU is found. The size matches the content exactly.
        / 配置は 1 回だけなので、GPU が 0 枚でも以後は移動できる。
          サイズは内容にピッタリ（余白なし）。
        """
        if self._placed:
            return
        self._placed = True
        self.root.update_idletasks()
        # Keep at least a minimum of 180 x 60 / 最小 180 x 60 保証
        w = max(self.root.winfo_reqwidth(), 180)
        h = max(self.root.winfo_reqheight(), 60)
        x, y = choose_position(self._saved_pos, self.root.winfo_screenwidth(),
                               self.root.winfo_screenheight(), w)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _move_top_right(self):
        """Menu handler: move the window to the top-right now.
        / メニューから: ウィンドウを今すぐ右上に移す。"""
        x, y = choose_position(None, self.root.winfo_screenwidth(),
                               self.root.winfo_screenheight(),
                               self.root.winfo_width())
        self.root.geometry(f"+{x}+{y}")

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

    # --- Process tooltip / プロセス一覧 -----------------------------
    def _on_card_enter(self, card):
        self._show_processes(card)

    def _on_card_leave(self, card):
        # <Leave> also fires when the pointer moves onto a child widget,
        # so check the position a moment later.
        # 子ウィジェットに移っただけでも <Leave> が来るので、少し後に
        # 位置を確かめる。
        def check():
            if self.tooltip.owner is card and not pointer_inside(card.frame):
                self.tooltip.hide()
        self.root.after(80, check)

    def _show_processes(self, card):
        try:
            text = format_processes(self.source.processes(card.index))
        except Exception as e:
            text = f"Error: {short_error(e)}"
        self.tooltip.show(card, card.frame,
                          f"Processes on GPU {card.index} ({card.name})"
                          f"\n\n{text}")

    # --- Cards / カード ---------------------------------------------
    def _rebuild_cards(self, gpus):
        """(Re)create one card per GPU. Called when the set of GPUs
        changes (e.g. an eGPU is connected or the driver is reloaded).
        / GPU ごとにカードを作り直す。GPU の構成が変わった時（eGPU の
          接続、ドライバの再読み込み等）に呼ばれる。"""
        self.tooltip.hide()
        for card in self.cards:
            card.frame.destroy()
        self.cards = []
        for g in gpus:
            if self.compact_var.get():
                card = CompactRow(self.cards_frame, g["index"], g["name"],
                                  self.style)
            else:
                card = GpuCard(self.cards_frame, g["index"], g["name"],
                               self.style, show_graph=self.graph_var.get())
            card.frame.bind("<Enter>",
                            lambda e, c=card: self._on_card_enter(c))
            card.frame.bind("<Leave>",
                            lambda e, c=card: self._on_card_leave(c))
            self.cards.append(card)
        self._card_keys = [(g["index"], g["name"]) for g in gpus]
        # Drop the history of GPUs that are gone / 消えた GPU の履歴は捨てる
        self.history = {k: h for k, h in self.history.items()
                        if k in self._card_keys}

    def _update_cards(self, gpus):
        """Show gpus (the latest query() result) on the cards.
        / gpus（直近の query() の結果）をカードに表示する。"""
        for card, g in zip(self.cards, gpus):
            card.update(g, self.history.get((g["index"], g["name"])))

    def close(self):
        """Save the window position, release the source, and quit.
        Called by the close button, the menu and SIGINT / SIGTERM.
        / ウィンドウ位置を保存し、ソースを解放して終了する。
          閉じるボタン・メニュー・SIGINT / SIGTERM から呼ばれる。
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
            update_config(x=int(m.group(1)), y=int(m.group(2)))
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
        self.tooltip.hide()
        self.source.close()
        self.root.destroy()

    def refresh(self):
        """Fetch the latest data, refresh every card, and reschedule.
        / 最新データを取得しカードを更新、次の更新を予約する。

        Cards are (re)built whenever the set of GPUs (index, name)
        changes; the window is placed on the first call.
        / GPU の構成 (index, name) が変わるたびにカードを作り直す。
          ウィンドウ配置は初回だけ。

        On error a short message is shown in the status line (details go
        to stderr once per distinct error) and the loop reschedules
        itself so the app keeps trying to recover.
        / エラー時は短いメッセージを状態行に表示し（詳細は同じエラーに
          つき 1 回だけ stderr へ）、ループを継続して復帰を試みる。
        """
        if self._closed:
            return
        # Called directly (not by the timer): drop the pending tick so only
        # one refresh loop runs. / タイマー以外から呼ばれた時は予約を消し、
        # 更新ループが 1 本だけになるようにする。
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
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
            self._after_id = self.root.after(self.interval_var.get(),
                                             self.refresh)
            return
        self._last_error = None
        self._last_gpus = gpus

        if [(g["index"], g["name"]) for g in gpus] != self._card_keys:
            self._rebuild_cards(gpus)

        # Record the graph history, then update each card
        # グラフ履歴に記録してから各カードを更新
        for g in gpus:
            key = (g["index"], g["name"])
            if key not in self.history:
                self.history[key] = History(self.graph_points)
            self.history[key].add(g["util"], g["temp"])
        self._update_cards(gpus)
        # Keep the process list current while it is shown
        # 表示中のプロセス一覧も更新する
        if self.tooltip.owner in self.cards:
            self._show_processes(self.tooltip.owner)

        # Status lines / 状態行
        n = len(self.cards)
        total_used = sum(g["mem_used"] for g in gpus)
        self.status.config(text=f"{n} GPU" + ("" if n == 1 else "s"), fg=DIM)
        self.mem_status.config(
            text=f"total memory: {fmt_mib(total_used)} used", fg=DIM)

        # Place once, then fit the window to the (possibly changed) content.
        # 初回配置のあと、ウィンドウを内容にフィットさせる。
        self._place_once()
        self.root.update_idletasks()
        self._fit()

        # Schedule the next tick / 次回の更新予約
        self._after_id = self.root.after(self.interval_var.get(), self.refresh)


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
    p.add_argument("--version", action="version",
                   version=f"%(prog)s {__version__}")
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
    p.add_argument("--new-instance", action="store_true",
                   help="open a new window even if one is already running "
                        "(default: bring the running one to the front)")
    args = p.parse_args()

    instance = None
    if not args.new_instance:
        instance = SingleInstance()
        if not instance.acquire():
            print("gpu_monitor: already running; brought its window to "
                  "the front (use --new-instance to open another)",
                  file=sys.stderr)
            return
    try:
        app = App(open_source(args.nvidia_smi),
                  always_on_top=args.always_on_top,
                  reset_position=args.reset_position)
        if instance:
            instance.attach(app.root, app.bring_to_front)
        # Ctrl+C / kill also save the position. The handler only
        # schedules close() so that Tk is touched from the main loop.
        # Ctrl+C / kill でも位置を保存する。ハンドラは close() の予約
        # だけ行い、Tk の操作はメインループから行う。
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: app._closed
                          or app.root.after(0, app.close))
        app.root.mainloop()
    finally:
        if instance:
            instance.close()


if __name__ == "__main__":
    main()
