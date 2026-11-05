# GPU Monitor — User Guide

This is a tiny program that allows you to monitor the "utilization," "memory usage," "power consumption," and "temperature" of the NVIDIA GPU(s) in your PC in real-time via a small window. No complex setup is required; just run it to start monitoring.

- Location: `~/programs/gpu_monitor/`
- Main file: `gpu_monitor.py`
- Requirements: Ubuntu (Desktop) + NVIDIA Drivers (`nvidia-smi` must be available)
- Theme: Dark theme for better readability.

---

## Information Displayed

For each GPU, the following items are displayed:

| Item | Example | Description |
|---|---|---|
| GPU Name | `GPU 0  NVIDIA GeForce GTX 1070` | Which GPU is being monitored |
| **GPU** (bar) | Green $\rightarrow$ Yellow $\rightarrow$ Red bar + % | GPU compute load (%) |
| **MEM** (bar) | Green $\rightarrow$ Yellow $\rightarrow$ Red bar + % | Memory utilization (%) |
| **PWR** (bar) | Green $\rightarrow$ Yellow $\rightarrow$ Red bar + % | Power draw vs. Power limit (%) |
| Detail Line | `7007/8192 MiB  77°C  60/230 W` | Memory used/total (MiB), Temp (°C), Power draw/limit (W) |
| Bottom Line | `2 GPUs total memory: 21863 MiB used` | Total number of GPUs and total memory used |

### Color Meaning (Bar colors)
- 🟢 **Green**: Below 70% (Plenty of headroom)
- 🟡 **Yellow**: 70–89% (Moderate load)
- 🔴 **Red**: 90% or above (Almost full)

> Absolute values for memory, temperature, and power are displayed in the small text line below the bars.

---

## How to Start

1. Open a terminal.
2. Run the following:

```bash
cd ~/programs/gpu_monitor
./gpu_monitor.py
```

- A window will appear at the **top-right** of the screen.
- The display is automatically updated approximately every **0.5 seconds**.
- To close the app, simply click the ✕ button on the window.

### Options (Command Line)

| Command | Meaning |
|---|---|
| `./gpu_monitor.py` | Normal start (remembers the last "Always on top" setting) |
| `./gpu_monitor.py -A` | **Force "Always on top"** from the start |
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
A. It is likely that `nvidia-smi` is not working (NVIDIA drivers are not installed or the GPU is not recognized). Please try running `nvidia-smi` directly in the terminal to check if GPU information is displayed.

**Q. I have two GPUs, but only one is shown.**
A. Check the number of recognized GPUs by running `nvidia-smi --query-gpu=name --format=csv,noheader`. It's possible the second GPU is not enabled in the drivers/settings.

**Q. The load is almost zero and the bar stays at 0%.**
A. This is normal. If there is no work for the GPU, it will be 0% (Green). Try playing a video or running a game to see it move.

**Q. Is it okay if the temperature is high?**
A. These values are for reference. Heat tolerance varies by GPU model. If the temperature rises sharply or the fan spins abnormally, please check your system environment.

**Q. The window doesn't appear after starting.**
A. Please check if your `DISPLAY` environment is correctly set. The program should appear if run from a terminal within a desktop environment.

---

## Config File

Saved in `~/.config/gpu_monitor.json`. Currently, only one item is stored:

```json
{ "always_on_top": true }
```

- `true`: Always on top ON (displayed at the very front)
- `false`: Always on top OFF (normal window)

To change this manually, open the file, switch `true`/`false`, save it, and restart `./gpu_monitor.py`.
(If the file is corrupted, the program will ignore it and boot with default settings.)

---

## File Locations

| Item | Path |
|---|---|
| Program | `~/programs/gpu_monitor/gpu_monitor.py` |
| User Guide (Japanese) | `~/programs/gpu_monitor/USER_J.md` |
| Developer Guide | `~/programs/gpu_monitor/DEVELOPER.md` |
| Config File | `~/.config/gpu_monitor.json` |
