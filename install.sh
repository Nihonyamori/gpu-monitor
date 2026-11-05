#!/bin/sh
# Register GPU Monitor in the desktop application menu (and optionally
# start it automatically at login).
# GPU Monitor をデスクトップのアプリメニューに登録する（ログイン時の
# 自動起動も選べる）。
#
#   ./install.sh               Add to the application menu / メニューに登録
#   ./install.sh --autostart   Also start at login / ログイン時にも起動
#   ./install.sh --uninstall   Remove menu, autostart and icons
#                              / メニュー・自動起動・アイコンを削除
set -eu

APP_ID=gpu-monitor
DIR=$(cd "$(dirname "$0")" && pwd)
DATA_DIR=${XDG_DATA_HOME:-$HOME/.local/share}
MENU_DIR=$DATA_DIR/applications
ICON_DIR=$DATA_DIR/icons/hicolor
AUTOSTART_DIR=${XDG_CONFIG_HOME:-$HOME/.config}/autostart

case "${1:-}" in
    --uninstall)
        rm -f "$MENU_DIR/$APP_ID.desktop" "$AUTOSTART_DIR/$APP_ID.desktop" \
              "$ICON_DIR/scalable/apps/$APP_ID.svg" \
              "$ICON_DIR/256x256/apps/$APP_ID.png"
        echo "Removed $APP_ID from the menu, autostart and icons."
        exit 0 ;;
    ""|--autostart) ;;
    *)
        echo "usage: $0 [--autostart | --uninstall]" >&2
        exit 2 ;;
esac

# The menu does not see the terminal's PATH (pyenv, conda, ...), so write
# the absolute path of a python3 that has tkinter into Exec.
# メニューからの起動ではターミナルの PATH（pyenv や conda）が効かないので、
# tkinter が使える python3 の絶対パスを Exec に書き込む。
if ! PY=$(python3 -c 'import sys, tkinter; print(sys.executable)' 2>/dev/null); then
    echo "error: python3 with tkinter not found in PATH" >&2
    exit 1
fi

# Icons: SVG for the menu (any size), PNG for older environments
# アイコン: メニュー用の SVG（任意サイズ）と、古い環境向けの PNG
mkdir -p "$ICON_DIR/scalable/apps" "$ICON_DIR/256x256/apps"
cp "$DIR/icon.svg" "$ICON_DIR/scalable/apps/$APP_ID.svg"
cp "$DIR/icon.png" "$ICON_DIR/256x256/apps/$APP_ID.png"

# StartupWMClass matches the window's WM_CLASS ("Gpu-monitor", from
# WM_CLASS in gpu_monitor.py), so the dock shows this entry's icon and
# name. Tk sends no startup notification, so StartupNotify=false avoids
# a busy cursor after launch.
# StartupWMClass はウィンドウの WM_CLASS（gpu_monitor.py の WM_CLASS
# による "Gpu-monitor"）と一致させ、Dock にこの項目のアイコンと名前を
# 出す。Tk は起動通知を送らないので、StartupNotify=false で起動後の
# 待ちカーソルを防ぐ。
mkdir -p "$MENU_DIR"
cat > "$MENU_DIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GPU Monitor
Comment=Show NVIDIA GPU usage, memory, power and temperature
Comment[ja]=NVIDIA GPU の使用率・メモリ・消費電力・温度を表示
Exec="$PY" "$DIR/gpu_monitor.py"
Icon=$APP_ID
Terminal=false
Categories=System;Monitor;
Keywords=GPU;NVIDIA;CUDA;nvidia-smi;monitor;
StartupNotify=false
StartupWMClass=Gpu-monitor
EOF
echo "Added to the application menu: $MENU_DIR/$APP_ID.desktop"
echo "  python: $PY"

if [ "${1:-}" = "--autostart" ]; then
    mkdir -p "$AUTOSTART_DIR"
    cp "$MENU_DIR/$APP_ID.desktop" "$AUTOSTART_DIR/$APP_ID.desktop"
    echo "Added to autostart:          $AUTOSTART_DIR/$APP_ID.desktop"
fi
