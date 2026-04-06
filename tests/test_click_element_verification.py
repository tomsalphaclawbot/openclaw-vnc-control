import importlib.util
import os
import shutil
from pathlib import Path

from PIL import Image, ImageDraw


_ROOT = Path(__file__).parent.parent
_SCRIPT = _ROOT / "vnc-control.py"

spec = importlib.util.spec_from_file_location("vnc_control", _SCRIPT)
vnc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vnc)


class CapturedResult(RuntimeError):
    def __init__(self, ok, data, error):
        super().__init__("captured result")
        self.ok = ok
        self.data = data or {}
        self.error = error


def _capture_result(monkeypatch):
    def fake_result_json(ok, data=None, error=None):
        raise CapturedResult(ok, data, error)

    monkeypatch.setattr(vnc, "result_json", fake_result_json)


def _mk_img(path: Path, changed: bool = False):
    img = Image.new("RGB", (200, 120), (10, 10, 10))
    if changed:
        draw = ImageDraw.Draw(img)
        draw.rectangle((40, 30, 170, 100), fill=(220, 220, 220))
    img.save(path)


def test_compute_image_change_metrics_detects_change(tmp_path):
    before = tmp_path / "before.png"
    after = tmp_path / "after.png"
    _mk_img(before, changed=False)
    _mk_img(after, changed=True)

    metrics = vnc.compute_image_change_metrics(str(before), str(after), threshold=10)

    assert metrics["changed"] is True
    assert metrics["changed_pixels"] > 0
    assert metrics["change_pct"] > 1.0
    assert metrics["bounding_box"] is not None


def test_click_element_retries_until_state_change(monkeypatch, tmp_path):
    _capture_result(monkeypatch)

    base_before = tmp_path / "base-before.png"
    base_same = tmp_path / "base-same.png"
    base_changed = tmp_path / "base-changed.png"
    _mk_img(base_before, changed=False)
    _mk_img(base_same, changed=False)
    _mk_img(base_changed, changed=True)

    monkeypatch.setattr(vnc, "capture_settings", lambda _args: ("ai", "jpeg", 0.5, 70))
    monkeypatch.setattr(
        vnc,
        "detect_element",
        lambda *args, **kwargs: {
            "found": True,
            "backend": "moondream",
            "center": {"x": 80, "y": 40},
        },
    )
    monkeypatch.setattr(vnc, "resolve_native_coords", lambda *args, **kwargs: (160, 80, 400, 240, 0.5))

    def fake_convert(src, out, fmt="jpeg", scale=None, quality=80):
        shutil.copy(src, out)
        try:
            if os.path.abspath(src) != os.path.abspath(out) and os.path.exists(src):
                os.unlink(src)
        except OSError:
            pass
        return out

    monkeypatch.setattr(vnc, "convert_screenshot", fake_convert)

    call_state = {"click_attempt": 0}

    def fake_run_vncdo(_config, actions, timeout=None, timeout_ok=False):
        if actions[:1] == ["capture"]:
            shutil.copy(base_before, actions[1])
            return True, "", "", 0.01

        if "capture" in actions:
            call_state["click_attempt"] += 1
            out_path = actions[actions.index("capture") + 1]
            if call_state["click_attempt"] == 1:
                shutil.copy(base_same, out_path)
            else:
                shutil.copy(base_changed, out_path)
            return True, "", "", 0.02

        return True, "", "", 0.01

    monkeypatch.setattr(vnc, "run_vncdo", fake_run_vncdo)

    class Args:
        description = "Allow button"
        backend = "moondream"
        button = "left"
        double = False
        verify_threshold = 10
        verify_min_change_pct = 0.05
        verify_retries = 2
        retry_offset = 7
        require_state_change = True

    try:
        vnc.cmd_click_element(Args(), config={})
        assert False, "expected CapturedResult"
    except CapturedResult as out:
        assert out.ok is True
        verification = out.data["verification"]
        assert verification["state_changed"] is True
        assert len(verification["attempts"]) == 2
        assert verification["attempts"][0]["state_changed"] is False
        assert verification["attempts"][1]["state_changed"] is True
        assert verification["attempts"][1]["offset_native"] != {"x": 0, "y": 0}


def test_click_element_can_require_state_change(monkeypatch, tmp_path):
    _capture_result(monkeypatch)

    base_before = tmp_path / "base-before.png"
    base_same = tmp_path / "base-same.png"
    _mk_img(base_before, changed=False)
    _mk_img(base_same, changed=False)

    monkeypatch.setattr(vnc, "capture_settings", lambda _args: ("ai", "jpeg", 0.5, 70))
    monkeypatch.setattr(
        vnc,
        "detect_element",
        lambda *args, **kwargs: {
            "found": True,
            "backend": "anthropic",
            "center": {"x": 80, "y": 40},
        },
    )
    monkeypatch.setattr(vnc, "resolve_native_coords", lambda *args, **kwargs: (160, 80, 400, 240, 0.5))

    def fake_convert(src, out, fmt="jpeg", scale=None, quality=80):
        shutil.copy(src, out)
        try:
            if os.path.abspath(src) != os.path.abspath(out) and os.path.exists(src):
                os.unlink(src)
        except OSError:
            pass
        return out

    monkeypatch.setattr(vnc, "convert_screenshot", fake_convert)

    def fake_run_vncdo(_config, actions, timeout=None, timeout_ok=False):
        if actions[:1] == ["capture"]:
            shutil.copy(base_before, actions[1])
            return True, "", "", 0.01
        if "capture" in actions:
            out_path = actions[actions.index("capture") + 1]
            shutil.copy(base_same, out_path)
            return True, "", "", 0.02
        return True, "", "", 0.01

    monkeypatch.setattr(vnc, "run_vncdo", fake_run_vncdo)

    class Args:
        description = "Allow button"
        backend = "remote"
        button = "left"
        double = False
        verify_threshold = 10
        verify_min_change_pct = 0.1
        verify_retries = 0
        retry_offset = 7
        require_state_change = True

    try:
        vnc.cmd_click_element(Args(), config={})
        assert False, "expected CapturedResult"
    except CapturedResult as out:
        assert out.ok is False
        assert "state change" in (out.error or "").lower()
        assert out.data["backend_requested"] == "remote"
        assert out.data["backend_used"] == "anthropic"
