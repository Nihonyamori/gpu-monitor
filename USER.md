# GPU Monitor — User Guide

This is a tiny program that allows you to monitor the "utilization," "memory usage," "power consumption," and "temperature" of the NVIDIA GPU(s) in your PC in real-time via a small window. No complex setup is required; just run it to start monitoring.

- Location: `~/programs/gpu_monitor/`
- Main file: `gpu_monitor.py`
- Requirements: Ubuntu (Desktop) + NVIDIA Drivers
- Theme: Dark theme for better readability.

---

## Information Displayed

For each GPU, the following items are displayed:

| Item | Example | Description |
|---|---|---|
| GPU Name | `GPU 0  NVIDIA GeForce GTX 1070` | Which GPU is being monitored |
| **GPU** (bar) | Green → Yellow → Red bar + % | GPU compute load (%) |
| **MEM** (bar) | Green → Yellow → Red bar + % | Memory utilization (%) |
| **PWR** (bar) | Green → Yellow → Red bar + % | Power draw vs. Power limit (%) |
| Detail Line | `6.8/8.0 GiB  77°C  60/230 W` | Memory used/total (GiB), Temp (°C), Power draw/limit (W) |
| History graph | Blue and orange lines | GPU utilization (blue, %) and temperature (orange, °C) over the last 60 seconds, on a 0–100 scale |
| Bottom Lines | `2 GPUs` / `total memory: 21.4 GiB used` | Number of GPUs (1st line) and total memory used (2nd line) |

### Color Meaning (Bar colors)
- 🟢 **Green**: Below 70% (Plenty of headroom)
- 🟡 **Yellow**: 70–89% (Moderate load)
- 🔴 **Red**: 90% or above (Almost full)

> Absolute values for memory, temperature, and power are displayed in the small text line below the bars.

The temperature turns 🟡 **yellow** at 80°C and 🔴 **red** at 90°C.

### Processes using a GPU

Move the mouse over a GPU card to see which processes are using it, next to the window:

```
    PID  USER             MEM  TYPE COMMAND
   3369  moni         268 MiB  G    Xorg vt2 -displayfd 3 ...
```

- `TYPE`: `C` = compute (CUDA etc.), `G` = graphics (desktop, browser), `C+G` = both
- The list is largest memory first and updates while the mouse stays on the card.
- Processes of other users or in containers may show `?` if they cannot be seen.

### Menu

Click the **⋮** button at the top-right of the window, or right-click anywhere in the window. Settings are saved for next time.

| Item | Meaning |
|---|---|
| Always on top | Same as the "Always on top" button |
| Compact view | Show each GPU on one line: `GPU 0  G 17%  M 9%  P 8%  48°C` (G = GPU, M = memory, P = power). The graphs and the total-memory line are hidden. Hover still shows the processes. |
| Show history graph (60 s) | Show / hide the graphs (not available in compact view) |
| Text size | Small / Medium / Large (fonts, bars and graphs) |
| Update interval | 0.5 s / 1 s / 2 s / 5 s. The graph always shows the last 60 seconds |
| Opacity | Make the window see-through: 100% / 90% / 80% / 70% / 60% |
| Move to top-right | Move the window back to the top-right corner |
| Quit | Close the app (the window position is saved) |
| GPU Monitor 1.1.0 | Version (cannot be clicked) |

---

## How to Start

> Installed with pipx (see README)? Just run `gpu-monitor`; it takes the same options as `./gpu_monitor.py`.

1. Open a terminal.
2. Run the following:

```bash
cd ~/programs/gpu_monitor
./gpu_monitor.py
```

- The first time, the window appears at the **top-right** of the screen. After that it opens **where you last closed it** (drag it anywhere you like).
- The display is automatically updated approximately every **0.5 seconds** (can be changed in the menu).
- To close the app, click the ✕ button on the window (or press Ctrl+C in the terminal). The window position is saved either way.

### Start from the application menu

Run this once in the terminal:

```bash
cd ~/programs/gpu_monitor
./install.sh               # add "GPU Monitor" to the application menu
./install.sh --autostart   # also start it automatically at login
```

To remove it (menu entry, autostart and icon), run `./install.sh --uninstall`. If you move the folder, run `./install.sh` again.

### Options (Command Line)

| Command | Meaning |
|---|---|
| `./gpu_monitor.py` | Normal start (remembers the last "Always on top" setting and window position) |
| `./gpu_monitor.py -A` | **Force "Always on top"** from the start |
| `./gpu_monitor.py --no-always-on-top` | Start **without** "Always on top" |
| `./gpu_monitor.py -R` | Start at the top-right, ignoring the saved position (if the window got lost) |
| `./gpu_monitor.py --nvidia-smi` | Read GPU data with the `nvidia-smi` command (see FAQ) |
| `./gpu_monitor.py --new-instance` | Open another window even if one is already running |
| `./gpu_monitor.py --version` | Show the version |
| `./gpu_monitor.py --help` | Show help/options |

---

## "Always on top" (Keep window on top)

If you want the window to stay visible and not be hidden behind other windows:

- Click the **"Always on top"** button at the top-right of the window to toggle it.
  - When the button is **Green**, it is ON (Always on top).
  - When the button is grey/dark, it is OFF.
- This state is **automatically saved**, so it will be remembered the next time you start the program.
  (Config file: `~/.config/gpu_monitor.json`)

> To keep it ON from the moment you launch, use the `-A` option.
> If you manually turn it OFF via the button, that setting takes priority and is saved.

---

## FAQ

**Q. I see an "Error: ..." message.**
A. The GPU information could not be read. The message tells you why:

| Message | Meaning |
|---|---|
| `NVML: ...` | The NVIDIA driver returned an error (e.g. `GPU is lost`, `Driver Not Loaded`) |
| `nvidia-smi not found` | The NVIDIA driver (`nvidia-smi` command) is not installed |
| `nvidia-smi failed (exit N)` | `nvidia-smi` ran but failed (e.g. driver not loaded, GPU not recognized) |
| `nvidia-smi timed out (2s)` | `nvidia-smi` did not answer within 2 seconds |

Run `nvidia-smi` directly in the terminal to check if GPU information is displayed. When started from a terminal, the full error message is also printed there. The display recovers automatically once the driver works again.

**Q. I have two GPUs, but only one is shown.**
A. Check the number of recognized GPUs by running `nvidia-smi --query-gpu=name --format=csv,noheader`. It's possible the second GPU is not enabled in the drivers/settings.

**Q. The load is almost zero and the bar stays at 0%.**
A. This is normal. If there is no work for the GPU, it will be 0% (Green). Try playing a video or running a game to see it move.

**Q. Is it okay if the temperature is high?**
A. These values are for reference. Heat tolerance varies by GPU model. If the temperature rises sharply or the fan spins abnormally, please check your system environment.

**Q. The window doesn't appear after starting.**
A. Please check if your `DISPLAY` environment is correctly set. The program should appear if run from a terminal within a desktop environment.
If it starts but you cannot see it (e.g. it was closed on a monitor that is now disconnected), start it with `./gpu_monitor.py -R` to bring it back to the top-right.

**Q. I started it again but no new window appeared.**
A. Only one window runs at a time; starting it again brings the running window to the front. To open another one anyway, use `./gpu_monitor.py --new-instance`.

**Q. The process list shows only some processes / no graphics processes.**
A. With `--nvidia-smi` (or when NVML is unavailable) only compute processes can be listed. Processes in containers or hidden by the system show `?`.

**Q. What is `--nvidia-smi` for?**
A. Normally the program reads the GPU data directly from the NVIDIA driver library (NVML), which is light and fast. If that library cannot be loaded, it automatically uses the `nvidia-smi` command instead. `--nvidia-smi` forces the latter; you normally do not need it.

---

## Config File

Saved in `~/.config/gpu_monitor.json`:

```json
{ "always_on_top": true, "show_graph": true, "compact": false, "opacity": 100,
  "text_size": "medium", "interval_ms": 500, "x": 2932, "y": 20 }
```

- `always_on_top`: `true` = Always on top ON (displayed at the very front), `false` = OFF (normal window)
- `show_graph`: `true` = show the history graphs (default), `false` = hide them
- `compact`: `true` = compact view, `false` = cards (default)
- `opacity`: `100`, `90`, `80`, `70` or `60` (%). Other values are treated as 100
- `text_size`: `small`, `medium` (default) or `large`
- `interval_ms`: update interval in ms: `500` (default), `1000`, `2000` or `5000`
- `x`, `y`: Window position (pixels from the top-left of the screen), saved when the app is closed

To change this manually, edit the file while the app is closed, then restart `./gpu_monitor.py`.
If the saved position is off-screen, the window is placed at the top-right instead.
(If the file is corrupted, the program will ignore it and boot with default settings.)

---

## File Locations

| Item | Path |
|---|---|
| Program | `~/programs/gpu_monitor/gpu_monitor.py` |
| Menu registration | `~/programs/gpu_monitor/install.sh` |
| Icon | `~/programs/gpu_monitor/icon.svg` / `icon.png` |
| User Guide (this file) | `~/programs/gpu_monitor/USER.md` |
| User Guide (Japanese) | `~/programs/gpu_monitor/USER_J.md` |
| Developer Guide | `~/programs/gpu_monitor/DEVELOPER.md` |
| Config File | `~/.config/gpu_monitor.json` |
