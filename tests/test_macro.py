"""
Phase 12: Macro recording and playback tests.

All tests are VNC-free (no live connection needed).
"""

import importlib.util
import json
import sys
import unittest
import tempfile
from contextlib import contextmanager
from pathlib import Path
from io import StringIO
from unittest.mock import patch

# Load vnc-control.py (hyphenated filename requires importlib)
_ROOT = Path(__file__).parent.parent
_SCRIPT = _ROOT / "vnc-control.py"
spec = importlib.util.spec_from_file_location("vnc_control", _SCRIPT)
vnc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vnc)  # type: ignore[union-attr]

cmd_macro = vnc.cmd_macro
_resolve_coords = vnc._resolve_coords


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextmanager
def capture_cmd(func, *args, **kwargs):
    """Run a cmd_* function, capture stdout JSON, tolerate SystemExit."""
    buf = StringIO()
    with patch("sys.stdout", buf):
        try:
            func(*args, **kwargs)
        except SystemExit:
            pass
    text = buf.getvalue().strip()
    yield json.loads(text) if text else {}


def _make_args(**kwargs):
    """Return a simple namespace mimicking argparse output."""
    defaults = {
        "subaction": "list",
        "macro_file": "",
        "delay_scale": 1.0,
        "continue_on_error": False,
    }
    defaults.update(kwargs)

    class A:
        pass

    a = A()
    for k, v in defaults.items():
        setattr(a, k, v)
    return a


def _dummy_config():
    return {"scale": 0.5, "native_width": 1920, "native_height": 1080}


# ---------------------------------------------------------------------------
# _resolve_coords
# ---------------------------------------------------------------------------

class TestResolveCoords(unittest.TestCase):

    def test_native_passthrough(self):
        x, y = _resolve_coords(100, 200, "native", _dummy_config())
        self.assertEqual((x, y), (100, 200))

    def test_screenshot_to_native_scale_half(self):
        # screenshot coords / 0.5 scale → native
        x, y = _resolve_coords(50, 100, "screenshot", _dummy_config())
        self.assertEqual((x, y), (100, 200))

    def test_screenshot_to_native_scale_one(self):
        cfg = {**_dummy_config(), "scale": 1.0}
        x, y = _resolve_coords(300, 400, "screenshot", cfg)
        self.assertEqual((x, y), (300, 400))

    def test_normalized_to_native(self):
        x, y = _resolve_coords(0.5, 0.5, "normalized", _dummy_config())
        self.assertEqual((x, y), (960, 540))

    def test_normalized_zero(self):
        x, y = _resolve_coords(0.0, 0.0, "normalized", _dummy_config())
        self.assertEqual((x, y), (0, 0))

    def test_normalized_one(self):
        x, y = _resolve_coords(1.0, 1.0, "normalized", _dummy_config())
        self.assertEqual((x, y), (1920, 1080))


# ---------------------------------------------------------------------------
# cmd_macro list
# ---------------------------------------------------------------------------

class TestMacroList(unittest.TestCase):

    def test_list_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            args = _make_args(subaction="list", macro_file=str(Path(td) / "missing.json"))
            with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                self.assertFalse(data["ok"])
                self.assertIn("not found", data["error"].lower())

    def test_list_valid_file(self):
        steps = [
            {"type": "click", "params": {"x": 10, "y": 20}, "delay_ms": 0},
            {"type": "type", "params": {"text": "hello"}, "delay_ms": 200},
        ]
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(steps, f)
            fname = f.name
        try:
            args = _make_args(subaction="list", macro_file=fname)
            with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                self.assertTrue(data["ok"])
                self.assertEqual(data["step_count"], 2)
                self.assertEqual(data["total_delay_ms"], 200)
        finally:
            Path(fname).unlink(missing_ok=True)

    def test_list_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump([], f)
            fname = f.name
        try:
            args = _make_args(subaction="list", macro_file=fname)
            with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                self.assertTrue(data["ok"])
                self.assertEqual(data["step_count"], 0)
        finally:
            Path(fname).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# cmd_macro record
# ---------------------------------------------------------------------------

class TestMacroRecord(unittest.TestCase):

    def test_record_creates_file(self):
        with tempfile.TemporaryDirectory() as td:
            fname = str(Path(td) / "out.json")
            steps_in = [
                '{"type":"click","params":{"x":10,"y":20}}',
                '{"type":"type","params":{"text":"hello"}}',
            ]
            stdin_data = "\n".join(steps_in) + "\n"
            args = _make_args(subaction="record", macro_file=fname)
            with patch("sys.stdin", StringIO(stdin_data)):
                with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                    self.assertTrue(data["ok"])
                    self.assertEqual(data["steps_added"], 2)
                    self.assertEqual(data["total_steps"], 2)
            # Verify written file
            saved = json.loads(Path(fname).read_text())
            self.assertEqual(len(saved), 2)
            self.assertEqual(saved[0]["type"], "click")
            self.assertEqual(saved[1]["type"], "type")

    def test_record_appends_to_existing(self):
        with tempfile.TemporaryDirectory() as td:
            fname = str(Path(td) / "out.json")
            existing = [{"type": "key", "params": {"keys": "Return"}, "delay_ms": 0}]
            Path(fname).write_text(json.dumps(existing))
            new_step = '{"type":"type","params":{"text":"world"}}'
            args = _make_args(subaction="record", macro_file=fname)
            with patch("sys.stdin", StringIO(new_step + "\n")):
                with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                    self.assertEqual(data["total_steps"], 2)
            saved = json.loads(Path(fname).read_text())
            self.assertEqual(saved[0]["type"], "key")
            self.assertEqual(saved[1]["type"], "type")

    def test_record_skips_invalid_json_lines(self):
        with tempfile.TemporaryDirectory() as td:
            fname = str(Path(td) / "out.json")
            stdin_data = 'not json\n{"type":"key","params":{"keys":"Return"}}\n'
            args = _make_args(subaction="record", macro_file=fname)
            with patch("sys.stdin", StringIO(stdin_data)):
                with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                    self.assertEqual(data["steps_added"], 1)

    def test_record_empty_stdin(self):
        with tempfile.TemporaryDirectory() as td:
            fname = str(Path(td) / "out.json")
            args = _make_args(subaction="record", macro_file=fname)
            with patch("sys.stdin", StringIO("")):
                with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                    self.assertTrue(data["ok"])
                    self.assertEqual(data["steps_added"], 0)


# ---------------------------------------------------------------------------
# cmd_macro play
# ---------------------------------------------------------------------------

class TestMacroPlay(unittest.TestCase):

    def _write_macro(self, steps, td):
        fname = str(Path(td) / "macro.json")
        Path(fname).write_text(json.dumps(steps))
        return fname

    def test_play_missing_file(self):
        with tempfile.TemporaryDirectory() as td:
            args = _make_args(subaction="play", macro_file=str(Path(td) / "nope.json"))
            with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                self.assertFalse(data["ok"])

    def test_play_wait_step(self):
        steps = [{"type": "wait", "params": {"ms": 1}, "delay_ms": 0}]
        with tempfile.TemporaryDirectory() as td:
            fname = self._write_macro(steps, td)
            args = _make_args(subaction="play", macro_file=fname)
            with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                self.assertTrue(data["ok"])
                self.assertEqual(data["steps_ok"], 1)

    def test_play_unknown_action_continue_on_error(self):
        steps = [{"type": "teleport", "params": {}, "delay_ms": 0}]
        with tempfile.TemporaryDirectory() as td:
            fname = self._write_macro(steps, td)
            args = _make_args(subaction="play", macro_file=fname, continue_on_error=True)
            with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                self.assertFalse(data["ok"])
                self.assertEqual(data["steps_failed"], 1)

    def test_play_delay_scale_zero_no_prestep_sleep(self):
        """With delay_scale=0 the pre-step sleep should be 0 (never called for >=1s)."""
        steps = [{"type": "wait", "params": {"ms": 1}, "delay_ms": 5000}]
        with tempfile.TemporaryDirectory() as td:
            fname = self._write_macro(steps, td)
            args = _make_args(subaction="play", macro_file=fname, delay_scale=0.0)
            slept = []

            def mock_sleep(s):
                slept.append(s)

            with patch("time.sleep", mock_sleep):
                with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                    self.assertTrue(data["ok"])
            # delay_scale=0 → pre-step sleep = 5000 * 0 = 0 → not called
            # The "wait" step itself calls sleep(1/1000)=0.001 — that's fine
            big_sleeps = [s for s in slept if s >= 1.0]
            self.assertEqual(big_sleeps, [])

    def test_play_empty_macro(self):
        with tempfile.TemporaryDirectory() as td:
            fname = self._write_macro([], td)
            args = _make_args(subaction="play", macro_file=fname)
            with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                self.assertTrue(data["ok"])
                self.assertEqual(data["steps_total"], 0)
                self.assertEqual(data["steps_ok"], 0)

    def test_play_abort_on_error_by_default(self):
        """Without --continue-on-error, first failure should abort."""
        steps = [
            {"type": "teleport", "params": {}, "delay_ms": 0},  # fails
            {"type": "wait", "params": {"ms": 1}, "delay_ms": 0},  # should not run
        ]
        with tempfile.TemporaryDirectory() as td:
            fname = self._write_macro(steps, td)
            args = _make_args(subaction="play", macro_file=fname, continue_on_error=False)
            with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                self.assertFalse(data["ok"])
                self.assertIn("aborted_at_step", data)
                self.assertEqual(data["aborted_at_step"], 0)
                # Only 1 result (the failed one, before abort)
                self.assertEqual(len(data["results"]), 1)

    def test_play_multi_step_all_wait(self):
        """Multiple wait steps should all succeed."""
        steps = [
            {"type": "wait", "params": {"ms": 1}, "delay_ms": 0},
            {"type": "wait", "params": {"ms": 1}, "delay_ms": 0},
            {"type": "wait", "params": {"ms": 1}, "delay_ms": 0},
        ]
        with tempfile.TemporaryDirectory() as td:
            fname = self._write_macro(steps, td)
            args = _make_args(subaction="play", macro_file=fname)
            with capture_cmd(cmd_macro, args, _dummy_config()) as data:
                self.assertTrue(data["ok"])
                self.assertEqual(data["steps_ok"], 3)
                self.assertEqual(data["steps_failed"], 0)


if __name__ == "__main__":
    unittest.main()
