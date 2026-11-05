"""Tests for gpu_monitor.py. / gpu_monitor.py のテスト。

Run from the repository root: / リポジトリ直下で実行:
    python3 -m unittest discover -s tests -v

No GPU is needed: nvidia-smi is replaced by small shell scripts and the
GUI tests use a fake data source. GUI tests are skipped without a
display (use `xvfb-run` on a headless machine).
/ GPU は不要。nvidia-smi は小さなシェルスクリプトで置き換え、GUI の
  テストは偽のデータソースを使う。ディスプレイが無ければ GUI のテストは
  スキップする（画面の無いマシンでは `xvfb-run` で実行）。
"""
import os
import select
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import gpu_monitor as gm  # noqa: E402


class TempDirTest(unittest.TestCase):
    """Gives each test a temp dir and a private config file.
    / テストごとに一時フォルダと専用の設定ファイルを用意する。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gm"))
        patcher = mock.patch.object(gm, "CONFIG_FILE",
                                    self.tmp / "config.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def fake_smi(self, script):
        """Put a fake nvidia-smi (sh script body) first on PATH.
        / 偽の nvidia-smi（sh スクリプト本体）を PATH の先頭に置く。"""
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir(exist_ok=True)
        smi = bin_dir / "nvidia-smi"
        smi.write_text("#!/bin/sh\n" + script)
        smi.chmod(0o755)
        patcher = mock.patch.dict(os.environ, {"PATH": str(bin_dir)})
        patcher.start()
        self.addCleanup(patcher.stop)


class TestHelpers(unittest.TestCase):
    def test_color_for_pct(self):
        self.assertEqual(gm.color_for_pct(0), gm.GOOD)
        self.assertEqual(gm.color_for_pct(69.9), gm.GOOD)
        self.assertEqual(gm.color_for_pct(70), gm.WARN)
        self.assertEqual(gm.color_for_pct(89.9), gm.WARN)
        self.assertEqual(gm.color_for_pct(90), gm.BAD)

    def test_color_for_temp(self):
        self.assertEqual(gm.color_for_temp(79), gm.DIM)
        self.assertEqual(gm.color_for_temp(80), gm.WARN)
        self.assertEqual(gm.color_for_temp(90), gm.BAD)

    def test_fmt_mib(self):
        self.assertEqual(gm.fmt_mib(512), "512 MiB")
        self.assertEqual(gm.fmt_mib(1024), "1.0 GiB")
        self.assertEqual(gm.fmt_mib(14907), "14.6 GiB")

    def test_fmt_mem_pair(self):
        self.assertEqual(gm.fmt_mem_pair(6648, 8192), "6.5/8.0 GiB")
        self.assertEqual(gm.fmt_mem_pair(18, 24576), "0.0/24.0 GiB")

    def test_make_gpu(self):
        g = gm.make_gpu(1, "X", 50, 30, 8192, 4096, 115, 230)
        self.assertEqual(g["mem_pct"], 50)
        self.assertEqual(g["power_pct"], 50)
        # No division by zero when totals are unknown / 0 除算しない
        g = gm.make_gpu(0, "X", 0, 0, 0, 0, 0, 0)
        self.assertEqual((g["mem_pct"], g["power_pct"]), (0.0, 0.0))

    def test_choose_position(self):
        self.assertEqual(gm.choose_position((500, 300), 1920, 1080, 250),
                         (500, 300))
        # Off screen, missing or not int -> top-right / 画面外・無し・非整数
        for saved in [(9000, 20), (100, 2000), (-5, 20), None, (None, None),
                      ("1", 2), (True, 2)]:
            self.assertEqual(gm.choose_position(saved, 1920, 1080, 250),
                             (1650, 20), saved)


class TestConfig(TempDirTest):
    def test_missing_corrupt_and_non_dict(self):
        self.assertEqual(gm.load_config(), {})
        gm.CONFIG_FILE.write_text("{broken")
        self.assertEqual(gm.load_config(), {})
        gm.CONFIG_FILE.write_text("[1, 2]")
        self.assertEqual(gm.load_config(), {})

    def test_update_config_merges(self):
        gm.update_config(always_on_top=True)
        gm.update_config(x=10, y=20)
        self.assertEqual(gm.load_config(),
                         {"always_on_top": True, "x": 10, "y": 20})


class TestSmiSource(TempDirTest):
    def test_query_gpus_parses_csv(self):
        self.fake_smi('echo "0, GPU A, 55, 30, 8192, 4096, 115.5, 230.00"\n'
                      'echo "3, GPU B, [N/A], 0, 24576, 18, [N/A], [N/A]"\n')
        a, b = gm.query_gpus()
        self.assertEqual((a["index"], a["name"], a["temp"]), (0, "GPU A", 55))
        self.assertEqual(a["mem_pct"], 50)
        self.assertAlmostEqual(a["power_pct"], 115.5 / 230 * 100)
        # [N/A] -> 0 and the index comes from nvidia-smi / [N/A] は 0
        self.assertEqual((b["index"], b["temp"], b["power_pct"]), (3, 0, 0))

    def test_processes(self):
        self.fake_smi('echo "1234, 512"\necho "99, [N/A]"\n')
        self.assertEqual(gm.SmiSource().processes(0),
                         [{"pid": 1234, "mem": 512, "kind": "C"},
                          {"pid": 99, "mem": None, "kind": "C"}])

    def test_short_errors(self):
        self.fake_smi("exit 9\n")
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            gm.query_gpus()
        self.assertEqual(gm.short_error(cm.exception),
                         "nvidia-smi failed (exit 9)")

        (self.tmp / "bin" / "nvidia-smi").unlink()
        with self.assertRaises(FileNotFoundError) as cm:
            gm.query_gpus()
        self.assertEqual(gm.short_error(cm.exception), "nvidia-smi not found")

        self.assertEqual(gm.short_error(gm.NvmlError("GPU is lost")),
                         "NVML: GPU is lost")
        self.assertEqual(gm.short_error(ValueError("x")), "ValueError")

    def test_timeout(self):
        self.fake_smi("exec /bin/sleep 5\n")
        with mock.patch.object(gm, "QUERY_TIMEOUT_S", 0.3):
            with self.assertRaises(subprocess.TimeoutExpired) as cm:
                gm.query_gpus()
            self.assertEqual(gm.short_error(cm.exception),
                             "nvidia-smi timed out (0.3s)")


class TestProcesses(unittest.TestCase):
    def test_describe_pid(self):
        user, name = gm.describe_pid(os.getpid())
        self.assertEqual(user, gm.pwd.getpwuid(os.getuid()).pw_name)
        self.assertIn("python", name)
        self.assertEqual(gm.describe_pid(2**22 + 12345), ("?", "?"))

    def test_format_processes(self):
        self.assertEqual(gm.format_processes(None),
                         "Process list not available")
        self.assertEqual(gm.format_processes([]), "No processes")
        procs = [{"pid": 2**22 + 1, "mem": None, "kind": "G"},
                 {"pid": os.getpid(), "mem": 2048, "kind": "C"},
                 {"pid": 2**22 + 2, "mem": 100, "kind": "C+G"}]
        lines = gm.format_processes(procs).splitlines()
        self.assertIn("PID", lines[0])
        # Largest memory first, unknown memory last / 大きい順、不明は最後
        self.assertIn("2.0 GiB", lines[1])
        self.assertIn("100 MiB", lines[2])
        self.assertIn(" C+G ", lines[2])
        self.assertIn(" G ", lines[3])

    def test_format_processes_limit(self):
        procs = [{"pid": 2**22 + i, "mem": i, "kind": "C"} for i in range(20)]
        text = gm.format_processes(procs, limit=5)
        self.assertIn("... 15 more", text)
        self.assertEqual(len(text.splitlines()), 1 + 5 + 1 + 1)


class TestSingleInstance(TempDirTest):
    def test_second_instance_signals_first(self):
        first = gm.SingleInstance(run_dir=str(self.tmp))
        self.assertTrue(first.acquire())
        second = gm.SingleInstance(run_dir=str(self.tmp))
        self.assertFalse(second.acquire())
        # The first instance's socket received a connection
        # 1 つ目のソケットに接続が来ている
        ready, _, _ = select.select([first.server], [], [], 2)
        self.assertEqual(ready, [first.server])
        first.close()
        self.assertFalse(first.sock_path.exists())
        # After the first one exits, a new one can start / 終了後は起動可
        third = gm.SingleInstance(run_dir=str(self.tmp))
        self.assertTrue(third.acquire())
        third.close()


class FakeSource:
    """Data source returning whatever the test puts in .gpus.
    / テストが .gpus に入れた値を返すデータソース。"""

    name = "fake"

    def __init__(self, gpus):
        self.gpus = gpus
        self.error = None
        self.closed = False

    def query(self):
        if self.error:
            raise self.error
        return self.gpus

    def processes(self, index):
        return [{"pid": os.getpid(), "mem": 300, "kind": "C"}]

    def close(self):
        self.closed = True


def gpu(index, temp=50, util=30, name="Fake GPU"):
    return gm.make_gpu(index, name, temp, util, 8192, 4096, 100, 200)


def have_display():
    try:
        tk.Tk().destroy()
        return True
    except tk.TclError:
        return False


@unittest.skipUnless(have_display(), "no display (use xvfb-run)")
class TestApp(TempDirTest):
    def make_app(self, gpus):
        self.source = FakeSource(gpus)
        app = gm.App(self.source, always_on_top=False)
        self.addCleanup(app.close)
        app.root.update()
        return app

    def test_cards_status_and_detail(self):
        app = self.make_app([gpu(0, temp=85)])
        self.assertEqual(len(app.cards), 1)
        self.assertEqual(app.status.cget("text"), "1 GPU")
        self.assertEqual(app.mem_status.cget("text"),
                         "total memory: 4.0 GiB used")
        card = app.cards[0]
        self.assertEqual(card.mem_lbl.cget("text"), "4.0/8.0 GiB")
        self.assertEqual(card.temp_lbl.cget("text"), "85°C")
        self.assertEqual(card.temp_lbl.cget("fg"), gm.WARN)

    def test_rebuild_when_gpus_change(self):
        app = self.make_app([gpu(0)])
        first_card = app.cards[0]
        app.refresh()
        self.assertIs(app.cards[0], first_card)   # same GPUs: kept / 維持
        self.source.gpus = [gpu(0), gpu(1)]
        app.refresh()
        self.assertEqual([c.index for c in app.cards], [0, 1])
        self.assertEqual(app.status.cget("text"), "2 GPUs")
        self.source.gpus = []
        app.refresh()
        self.assertEqual(app.cards, [])
        self.assertEqual(app.status.cget("text"), "0 GPUs")

    def test_error_keeps_short_message(self):
        app = self.make_app([gpu(0)])
        self.source.error = gm.NvmlError("GPU is lost")
        with mock.patch("sys.stderr"):
            app.refresh()
        self.assertEqual(app.status.cget("text"), "Error: NVML: GPU is lost")

    def test_graph_history_and_toggle(self):
        app = self.make_app([gpu(0)])
        for _ in range(gm.GRAPH_POINTS + 10):
            app.refresh()
        graph = app.cards[0].graph
        self.assertEqual(len(graph.util), gm.GRAPH_POINTS)
        self.assertTrue(graph.canvas.winfo_ismapped())
        app.graph_var.set(False)
        app._toggle_graph()
        app.root.update()
        self.assertFalse(graph.canvas.winfo_ismapped())
        self.assertEqual(gm.load_config()["show_graph"], False)

    def test_topmost_and_position_saved(self):
        app = self.make_app([gpu(0)])
        app._save_topmost(True)
        self.assertTrue(app.topmost_var.get())
        self.assertEqual(gm.load_config()["always_on_top"], True)
        app.root.geometry("+300+200")
        app.root.update()
        app.close()
        self.assertTrue(self.source.closed)
        cfg = gm.load_config()
        self.assertEqual((cfg["x"], cfg["y"]), (300, 200))

    def test_second_instance_raises_window(self):
        app = self.make_app([gpu(0)])
        first = gm.SingleInstance(run_dir=str(self.tmp))
        self.assertTrue(first.acquire())
        self.addCleanup(first.close)
        with mock.patch.object(app, "bring_to_front") as raise_:
            first.attach(app.root, app.bring_to_front)
            self.assertFalse(gm.SingleInstance(run_dir=str(self.tmp)).acquire())
            for _ in range(50):
                app.root.update()
                if raise_.called:
                    break
                app.root.after(20)
            raise_.assert_called_once()
        app.root.tk.deletefilehandler(first.server)

    def test_process_tooltip(self):
        app = self.make_app([gpu(0)])
        app._show_processes(app.cards[0])
        app.root.update()
        text = app.tooltip.label.cget("text")
        self.assertIn("Processes on GPU 0", text)
        self.assertIn("300 MiB", text)
        self.assertIs(app.tooltip.owner, app.cards[0])
        app.tooltip.hide()
        self.assertIsNone(app.tooltip.win)

    def test_compact_view(self):
        app = self.make_app([gpu(0, temp=92, util=75), gpu(1)])
        app.compact_var.set(True)
        app._toggle_compact()
        app.root.update()
        self.assertTrue(all(isinstance(c, gm.CompactRow) for c in app.cards))
        row = app.cards[0]
        self.assertEqual(row.pct_lbls["util"].cget("text"), "75%")
        self.assertEqual(row.pct_lbls["util"].cget("fg"), gm.WARN)
        self.assertEqual(row.temp_lbl.cget("fg"), gm.BAD)
        self.assertFalse(app.mem_status.winfo_ismapped())
        self.assertEqual(app.menu.entrycget(gm.GRAPH_MENU_LABEL, "state"),
                         "disabled")
        self.assertEqual(gm.load_config()["compact"], True)
        # Rows survive refreshes and are smaller than cards / 更新後も維持
        app.refresh()
        self.assertIsInstance(app.cards[0], gm.CompactRow)
        compact_h = app.root.winfo_reqheight()
        app.compact_var.set(False)
        app._toggle_compact()
        app.root.update()
        self.assertIsInstance(app.cards[0], gm.GpuCard)
        self.assertGreater(app.root.winfo_reqheight(), compact_h)
        self.assertEqual(app.menu.entrycget(gm.GRAPH_MENU_LABEL, "state"),
                         "normal")

    def test_compact_view_restored_from_config(self):
        gm.update_config(compact=True, opacity=80)
        app = self.make_app([gpu(0)])
        self.assertIsInstance(app.cards[0], gm.CompactRow)
        self.assertEqual(app.opacity_var.get(), 80)

    def test_opacity(self):
        app = self.make_app([gpu(0)])
        self.assertAlmostEqual(float(app.root.wm_attributes("-alpha")), 1.0)
        app.opacity_var.set(70)
        app._set_opacity()
        self.assertAlmostEqual(float(app.root.wm_attributes("-alpha")), 0.7,
                               places=2)
        self.assertEqual(gm.load_config()["opacity"], 70)

    def test_invalid_opacity_in_config(self):
        gm.update_config(opacity=5)
        app = self.make_app([gpu(0)])
        self.assertEqual(app.opacity_var.get(), 100)

    def test_menu_button_and_version_entry(self):
        app = self.make_app([gpu(0)])
        self.assertEqual(app.menu_btn.cget("text"), "⋮")
        last = app.menu.index("end")
        self.assertEqual(app.menu.entrycget(last, "label"),
                         f"GPU Monitor {gm.__version__}")


class TestVersion(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent

    def test_version_option(self):
        out = subprocess.run(
            [sys.executable, str(self.ROOT / "gpu_monitor.py"), "--version"],
            capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.strip(), f"gpu_monitor.py {gm.__version__}")

    def test_changelog_has_current_version(self):
        changelog = (self.ROOT / "CHANGELOG.md").read_text()
        self.assertIn(f"## [{gm.__version__}]", changelog)


if __name__ == "__main__":
    unittest.main()
