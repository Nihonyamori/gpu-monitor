#!/bin/sh
# Register GPU Monitor in the desktop application menu (and optionally
# start it automatically at login).
# GPU Monitor をデスクトップのアプリメニューに登録する（ログイン時の
# 自動起動も選べる）。
#
#   ./install.sh               Add to the application menu / メニューに登録
#   ./install.sh --autostart   Also start at login / ログイン時にも起動
#   ./install.sh --uninstall   Remove both / 両方を削除
set -eu

APP_ID=gpu-monitor
DIR=$(cd "$(dirname "$0")" && pwd)
MENU_DIR=${XDG_DATA_HOME:-$HOME/.local/share}/applications
AUTOSTART_DIR=${XDG_CONFIG_HOME:-$HOME/.config}/autostart

case "${1:-}" in
    --uninstall)
        rm -f "$MENU_DIR/$APP_ID.desktop" "$AUTOSTART_DIR/$APP_ID.desktop"
        echo "Removed $APP_ID.desktop from the menu and autostart."
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

mkdir -p "$MENU_DIR"
cat > "$MENU_DIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GPU Monitor
Comment=Show NVIDIA GPU usage, memory, power and temperature
Exec="$PY" "$DIR/gpu_monitor.py"
Icon=utilities-system-monitor
Terminal=false
Categories=System;Monitor;
EOF
echo "Added to the application menu: $MENU_DIR/$APP_ID.desktop"
echo "  python: $PY"

if [ "${1:-}" = "--autostart" ]; then
    mkdir -p "$AUTOSTART_DIR"
    cp "$MENU_DIR/$APP_ID.desktop" "$AUTOSTART_DIR/$APP_ID.desktop"
    echo "Added to autostart:          $AUTOSTART_DIR/$APP_ID.desktop"
fi
