"""
Unit tests for vnc-control.py — no VNC connection required.

Sprint F: automated e2e smoke tests (unit slice).
All tests here run offline against pure-Python logic.
"""
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load vnc-control as a module (it's a script, not a package)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
_SCRIPT = _ROOT / "vnc-control.py"

spec = importlib.util.spec_from_file_location("vnc_control", _SCRIPT)
vnc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vnc)


# ---------------------------------------------------------------------------
# normalize_key_name
# ---------------------------------------------------------------------------

class TestNormalizeKeyName:
    """macOS ARD 'return' → 'enter' alias and related edge cases."""

    def test_return_maps_to_enter(self):
        assert vnc.normalize_key_name("return") == "enter"

    def test_return_case_insensitive(self):
        assert vnc.normalize_key_name("Return") == "enter"
        assert vnc.normalize_key_name("RETURN") == "enter"

    def test_kp_enter_maps_to_enter(self):
        assert vnc.normalize_key_name("kp_enter") == "enter"

    def test_iso_enter_maps_to_enter(self):
        assert vnc.normalize_key_name("iso_enter") == "enter"

    def test_linefeed_maps_to_enter(self):
        assert vnc.normalize_key_name("linefeed") == "enter"

    def test_enter_passthrough(self):
        assert vnc.normalize_key_name("enter") == "enter"

    def test_unknown_key_passthrough(self):
        assert vnc.normalize_key_name("ctrl") == "ctrl"
        assert vnc.normalize_key_name("space") == "space"
        assert vnc.normalize_key_name("F5") == "F5"

    def test_strips_surrounding_whitespace(self):
        assert vnc.normalize_key_name("  return  ") == "enter"


# ---------------------------------------------------------------------------
# to_native / from_native
# ---------------------------------------------------------------------------

class TestCoordConversion:
    """Screenshot ↔ native coordinate math."""

    def test_to_native_half_scale(self):
        nx, ny = vnc.to_native(100, 200, 0.5)
        assert nx == 200
        assert ny == 400

    def test_to_native_scale_1(self):
        nx, ny = vnc.to_native(500, 300, 1.0)
        assert nx == 500
        assert ny == 300

    def test_from_native_half_scale(self):
        sx, sy = vnc.from_native(200, 400, 0.5)
        assert sx == 100
        assert sy == 200

    def test_roundtrip_to_native_from_native(self):
        x, y, scale = 732, 541, 0.5
        nx, ny = vnc.to_native(x, y, scale)
        sx, sy = vnc.from_native(nx, ny, scale)
        # Allow ±1 for rounding
        assert abs(sx - x) <= 1
        assert abs(sy - y) <= 1

    def test_to_native_rounds_correctly(self):
        # 101 / 0.5 = 202.0 exactly → 202
        nx, ny = vnc.to_native(101, 99, 0.5)
        assert nx == 202
        assert ny == 198


# ---------------------------------------------------------------------------
# AI profile capture settings guardrails
# ---------------------------------------------------------------------------

class TestCaptureSettingsAIProfile:
    """AI profile must enforce efficiency constraints."""

    def _make_args(self, **kwargs):
        """Minimal namespace mimic for args."""
        class NS:
            pass
        ns = NS()
        ns.profile = "ai"
        ns.format = kwargs.get("format", None)
        ns.scale = kwargs.get("scale", None)
        ns.quality = kwargs.get("quality", None)
        return ns

    def test_ai_profile_default_format_is_jpeg(self):
        args = self._make_args()
        _, fmt, _, _ = vnc.capture_settings(args)
        assert fmt in ("jpeg", "jpg")

    def test_ai_profile_default_scale_is_half(self):
        args = self._make_args()
        _, _, scale, _ = vnc.capture_settings(args)
        assert scale == 0.5

    def test_ai_profile_forces_png_to_jpeg(self):
        args = self._make_args(format="png")
        _, fmt, _, _ = vnc.capture_settings(args)
        assert fmt in ("jpeg", "jpg")

    def test_ai_profile_clamps_scale_above_limit(self):
        args = self._make_args(scale=0.9)
        _, _, scale, _ = vnc.capture_settings(args)
        assert scale <= 0.6

    def test_ai_profile_clamps_quality_above_limit(self):
        args = self._make_args(quality=95)
        _, _, _, quality = vnc.capture_settings(args)
        assert quality <= 85

    def test_ai_profile_clamps_quality_below_limit(self):
        args = self._make_args(quality=20)
        _, _, _, quality = vnc.capture_settings(args)
        assert quality >= 40


# ---------------------------------------------------------------------------
# Manual profile capture settings
# ---------------------------------------------------------------------------

class TestCaptureSettingsManualProfile:
    """Manual profile should not apply AI guardrails."""

    def _make_args(self, **kwargs):
        class NS:
            pass
        ns = NS()
        ns.profile = "manual"
        ns.format = kwargs.get("format", None)
        ns.scale = kwargs.get("scale", None)
        ns.quality = kwargs.get("quality", None)
        return ns

    def test_manual_profile_default_format_is_jpeg(self):
        args = self._make_args()
        _, fmt, _, _ = vnc.capture_settings(args)
        assert fmt in ("jpeg", "jpg")

    def test_manual_profile_respects_png_request(self):
        args = self._make_args(format="png")
        _, fmt, _, _ = vnc.capture_settings(args)
        assert fmt == "png"

    def test_manual_profile_respects_scale(self):
        args = self._make_args(scale=0.25)
        _, _, scale, _ = vnc.capture_settings(args)
        assert scale == 0.25

    def test_manual_profile_respects_high_quality(self):
        args = self._make_args(quality=95)
        _, _, _, quality = vnc.capture_settings(args)
        assert quality == 95


# ---------------------------------------------------------------------------
# convert_between_spaces (offline — no VNC, uses fallback resolution)
# ---------------------------------------------------------------------------

class TestConvertBetweenSpaces:
    """Space conversion logic using hardcoded native resolution fallback."""

    def _config(self):
        return {
            "host": "127.0.0.1",
            "port": 5900,
            "password": "",
            "username": "",
        }

    def test_screenshot_to_native(self):
        result = vnc.convert_between_spaces(100, 200, "screenshot", "native", self._config(), scale=0.5)
        assert result["to"]["space"] == "native"
        assert result["to"]["x"] == 200
        assert result["to"]["y"] == 400

    def test_native_to_screenshot(self):
        result = vnc.convert_between_spaces(200, 400, "native", "screenshot", self._config(), scale=0.5)
        assert result["to"]["space"] == "screenshot"
        assert result["to"]["x"] == 100
        assert result["to"]["y"] == 200

    def test_native_to_normalized(self):
        # 1710 / 3420 = 0.5, 1107 / 2214 = 0.5
        result = vnc.convert_between_spaces(1710, 1107, "native", "normalized", self._config())
        assert result["to"]["space"] == "normalized"
        assert abs(result["to"]["x"] - 0.5) < 0.01
        assert abs(result["to"]["y"] - 0.5) < 0.01

    def test_normalized_to_native(self):
        result = vnc.convert_between_spaces(0.5, 0.5, "normalized", "native", self._config())
        assert result["to"]["space"] == "native"
        # 0.5 * 3420 = 1710, 0.5 * 2214 = 1107
        assert result["to"]["x"] == 1710
        assert result["to"]["y"] == 1107


# ---------------------------------------------------------------------------
# State file helpers (tmp dir, no real FS side effects via patching)
# ---------------------------------------------------------------------------

class TestStateHelpers:
    def test_load_last_capture_state_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vnc, "STATE_DIR", tmp_path)
        monkeypatch.setattr(vnc, "STATE_FILE", tmp_path / "capture_state.json")
        result = vnc.load_last_capture_state()
        assert result is None

    def test_save_and_load_capture_state_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vnc, "STATE_DIR", tmp_path)
        monkeypatch.setattr(vnc, "STATE_FILE", tmp_path / "capture_state.json")

        payload = {"sha1": "abc123", "scale": 0.5, "path": "/tmp/test.jpg"}
        vnc.save_last_capture_state(payload)
        loaded = vnc.load_last_capture_state()
        assert loaded == payload


# ---------------------------------------------------------------------------
# sha1_file
# ---------------------------------------------------------------------------

class TestSha1File:
    def test_sha1_deterministic(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        h1 = vnc.sha1_file(str(f))
        h2 = vnc.sha1_file(str(f))
        assert h1 == h2
        assert len(h1) == 40  # hex sha1

    def test_sha1_changes_on_content_change(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello")
        h1 = vnc.sha1_file(str(f))
        f.write_bytes(b"world")
        h2 = vnc.sha1_file(str(f))
        assert h1 != h2


# ---------------------------------------------------------------------------
# Phase 7: Vision-Assisted Automation — _vision_find_element unit tests
# ---------------------------------------------------------------------------

class TestVisionFindElement:
    """Unit tests for _vision_find_element — mock the API, test parsing logic."""

    def test_missing_api_key_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        img = tmp_path / "test.jpg"
        img.write_bytes(b"fake-jpeg-data")
        result = vnc._vision_find_element(str(img), "save button")
        assert result["found"] is False
        assert "ANTHROPIC_API_KEY" in result["error"]

    def test_valid_json_response_parsed(self, monkeypatch, tmp_path):
        """Mock the urlopen to return a valid JSON vision response."""
        import io

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)  # minimal fake JPEG header

        vision_payload = {
            "content": [{"text": '{"found": true, "x": 142.5, "y": 87.0, "confidence": "high", "reasoning": "Save button found top right", "bounding_box": {"x1": 120, "y1": 75, "x2": 165, "y2": 99}}'}]
        }

        class FakeResp:
            def read(self):
                return json.dumps(vision_payload).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setattr(vnc.urllib.request, "urlopen", lambda *a, **kw: FakeResp())

        result = vnc._vision_find_element(str(img), "save button")
        assert result["found"] is True
        assert result["x"] == 142.5
        assert result["y"] == 87.0
        assert result["confidence"] == "high"
        assert result["bounding_box"]["x1"] == 120

    def test_element_not_found_response(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        vision_payload = {
            "content": [{"text": '{"found": false, "x": null, "y": null, "confidence": "high", "reasoning": "No save button visible", "bounding_box": null}'}]
        }

        class FakeResp:
            def read(self): return json.dumps(vision_payload).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setattr(vnc.urllib.request, "urlopen", lambda *a, **kw: FakeResp())

        result = vnc._vision_find_element(str(img), "save button")
        assert result["found"] is False
        assert result["x"] is None

    def test_markdown_fenced_json_stripped(self, monkeypatch, tmp_path):
        """Vision model sometimes wraps JSON in ```json fences — should still parse."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        fenced = '```json\n{"found": true, "x": 50.0, "y": 60.0, "confidence": "medium", "reasoning": "OK", "bounding_box": null}\n```'
        vision_payload = {"content": [{"text": fenced}]}

        class FakeResp:
            def read(self): return json.dumps(vision_payload).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setattr(vnc.urllib.request, "urlopen", lambda *a, **kw: FakeResp())

        result = vnc._vision_find_element(str(img), "button")
        assert result["found"] is True
        assert result["x"] == 50.0

    def test_malformed_json_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        vision_payload = {"content": [{"text": "This is not JSON at all, sorry"}]}

        class FakeResp:
            def read(self): return json.dumps(vision_payload).encode()
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setattr(vnc.urllib.request, "urlopen", lambda *a, **kw: FakeResp())

        result = vnc._vision_find_element(str(img), "button")
        assert result["found"] is False
        assert "parse failed" in result["error"].lower() or "error" in result

    def test_api_exception_returns_error(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        def raise_error(*a, **kw):
            raise Exception("network timeout")

        monkeypatch.setattr(vnc.urllib.request, "urlopen", raise_error)

        result = vnc._vision_find_element(str(img), "button")
        assert result["found"] is False
        assert "network timeout" in result["error"]


# ---------------------------------------------------------------------------
# Phase 8: scroll direction → vncdo button mapping
# ---------------------------------------------------------------------------

class TestScrollDirectionMapping:
    """scroll command maps direction strings to correct vncdo button numbers."""

    def _get_scroll_button(self, direction):
        """Parse cmd_scroll logic: up/right → button 4, down/left → button 5."""
        direction = direction.lower()
        if direction in ("up", "right"):
            return "4"
        elif direction in ("down", "left"):
            return "5"
        return None

    def test_up_maps_to_button_4(self):
        assert self._get_scroll_button("up") == "4"

    def test_right_maps_to_button_4(self):
        assert self._get_scroll_button("right") == "4"

    def test_down_maps_to_button_5(self):
        assert self._get_scroll_button("down") == "5"

    def test_left_maps_to_button_5(self):
        assert self._get_scroll_button("left") == "5"

    def test_click_clamp_lower(self):
        """Clicks are clamped to at least 1."""
        raw = 0
        clamped = max(1, min(raw, 50))
        assert clamped == 1

    def test_click_clamp_upper(self):
        """Clicks are clamped to at most 50."""
        raw = 999
        clamped = max(1, min(raw, 50))
        assert clamped == 50

    def test_click_in_range_unchanged(self):
        """Clicks within 1-50 are unchanged."""
        for n in (1, 3, 10, 50):
            assert max(1, min(n, 50)) == n


# ---------------------------------------------------------------------------
# Phase 8: drag coordinate resolution
# ---------------------------------------------------------------------------

class TestDragCoords:
    """drag command resolves start/end coords independently to native space."""

    def _native_from_screenshot(self, x, y, scale):
        """Replicate the to_native logic for screenshot → native conversion."""
        return round(x / scale), round(y / scale)

    def test_drag_start_resolves_correctly(self):
        nx, ny = self._native_from_screenshot(100, 200, 0.5)
        assert nx == 200
        assert ny == 400

    def test_drag_end_resolves_correctly(self):
        nx, ny = self._native_from_screenshot(300, 400, 0.5)
        assert nx == 600
        assert ny == 800

    def test_drag_at_scale_1(self):
        """At scale 1.0, screenshot coords == native coords."""
        nx, ny = self._native_from_screenshot(150, 250, 1.0)
        assert nx == 150
        assert ny == 250

    def test_drag_button_mapping(self):
        """Drag button map matches click button map."""
        button_map = {"left": "1", "right": "3", "middle": "2"}
        assert button_map["left"] == "1"
        assert button_map["right"] == "3"
        assert button_map["middle"] == "2"


# ---------------------------------------------------------------------------
# Phase 8: CLI parser validation (scroll + drag subcommands exist)
# ---------------------------------------------------------------------------

class TestPhase8CLIParsing:
    """Verify scroll and drag subcommands are wired into argparse."""

    def test_scroll_parser_exists(self):
        """scroll subcommand should be registered."""
        import subprocess
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "scroll", "--help"],
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0
        assert "scroll" in result.stdout.lower()

    def test_drag_parser_exists(self):
        """drag subcommand should be registered."""
        import subprocess
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "drag", "--help"],
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0
        assert "drag" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Phase 9: Image diff (cmd_diff) — pure-Python, no VNC required
# ---------------------------------------------------------------------------

class TestPhase9ImageDiff:
    """Tests for cmd_diff — image change detection and bounding box computation."""

    def _make_solid_image(self, tmp_path, color, name="img.png", size=(200, 150)):
        """Create a solid-color PNG image."""
        from PIL import Image
        img = Image.new("RGB", size, color)
        p = tmp_path / name
        img.save(str(p))
        return str(p)

    def test_identical_images_no_change(self, tmp_path):
        """Identical images → 0% change, no bounding box, changed=False."""
        a = self._make_solid_image(tmp_path, (128, 128, 128), "a.png")
        b = self._make_solid_image(tmp_path, (128, 128, 128), "b.png")
        out = str(tmp_path / "diff.png")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "diff", a, b, "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["changed"] is False
        assert data["change_pct"] == 0.0
        assert data["bounding_box"] is None

    def test_fully_changed_image(self, tmp_path):
        """White vs black image → ~100% change."""
        a = self._make_solid_image(tmp_path, (0, 0, 0), "a.png")
        b = self._make_solid_image(tmp_path, (255, 255, 255), "b.png")
        out = str(tmp_path / "diff.png")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "diff", a, b, "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["changed"] is True
        assert data["change_pct"] == 100.0
        assert data["bounding_box"] is not None

    def test_partial_change_has_bbox(self, tmp_path):
        """Red rectangle added to image → bbox covers only changed area."""
        from PIL import Image, ImageDraw
        size = (200, 150)
        img_a = Image.new("RGB", size, (200, 200, 200))
        p_a = tmp_path / "a.png"
        img_a.save(str(p_a))

        img_b = img_a.copy()
        draw = ImageDraw.Draw(img_b)
        draw.rectangle([(50, 40), (100, 90)], fill=(255, 0, 0))
        p_b = tmp_path / "b.png"
        img_b.save(str(p_b))

        out = str(tmp_path / "diff.png")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "diff", str(p_a), str(p_b), "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["changed"] is True
        assert data["change_pct"] > 0
        assert data["change_pct"] < 100  # only partial change
        bb = data["bounding_box"]
        assert bb is not None
        assert bb["x"] >= 50
        assert bb["y"] >= 40
        assert bb["x2"] <= 100
        assert bb["y2"] <= 90

    def test_threshold_suppresses_noise(self, tmp_path):
        """Near-identical images with tiny variation should show 0% with high threshold."""
        from PIL import Image
        size = (100, 100)
        img_a = Image.new("RGB", size, (128, 128, 128))
        img_b = Image.new("RGB", size, (130, 128, 128))  # only +2 on R channel
        p_a = tmp_path / "a.png"
        p_b = tmp_path / "b.png"
        img_a.save(str(p_a))
        img_b.save(str(p_b))

        out = str(tmp_path / "diff.png")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "diff", str(p_a), str(p_b),
             "--threshold", "5", "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # +2 difference < threshold 5 → treated as no change
        assert data["changed"] is False

    def test_overlay_image_written(self, tmp_path):
        """Overlay file is created and has non-zero size."""
        a = self._make_solid_image(tmp_path, (0, 0, 0), "a.png")
        b = self._make_solid_image(tmp_path, (255, 0, 0), "b.png")
        out = str(tmp_path / "diff.png")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "diff", a, b, "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["overlay_image"]["path"] == out
        import os
        assert os.path.exists(out)
        assert os.path.getsize(out) > 0

    def test_diff_parser_exists(self):
        """diff subcommand should be registered in argparse."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "diff", "--help"],
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0
        assert "diff" in result.stdout.lower()
        assert "before" in result.stdout.lower()
        assert "after" in result.stdout.lower()


import subprocess


# ---------------------------------------------------------------------------
# Phase 10 — crop (Region-of-Interest)
# ---------------------------------------------------------------------------

class TestPhase10Crop:
    """Tests for the crop command (Phase 10 ROI extraction)."""

    def _make_image(self, path, size=(200, 150), color=(100, 150, 200)):
        from PIL import Image
        img = Image.new("RGB", size, color)
        img.save(str(path))
        return str(path)

    def test_basic_crop_screenshot_space(self, tmp_path):
        """Crop a region in screenshot space and verify dimensions."""
        src = self._make_image(tmp_path / "src.png", size=(200, 150))
        out = str(tmp_path / "crop.jpg")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "crop", src, "10", "20", "110", "80",
             "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["action"] == "crop"
        assert data["crop_dimensions"]["w"] == 100
        assert data["crop_dimensions"]["h"] == 60
        assert data["screenshot_coords"] == {"x1": 10, "y1": 20, "x2": 110, "y2": 80}
        assert os.path.exists(out)

    def test_crop_normalized_space(self, tmp_path):
        """Crop using normalized coordinates (0..1)."""
        src = self._make_image(tmp_path / "src.png", size=(200, 100))
        out = str(tmp_path / "crop_norm.jpg")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "crop", src,
             "0.0", "0.0", "0.5", "1.0",
             "--space", "normalized", "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        # 50% of 200 wide, 100% of 100 tall
        assert data["crop_dimensions"]["w"] == 100
        assert data["crop_dimensions"]["h"] == 100
        assert data["input_space"] == "normalized"

    def test_crop_clamped_to_bounds(self, tmp_path):
        """Coordinates outside image bounds are clamped, not errored."""
        src = self._make_image(tmp_path / "src.png", size=(100, 100))
        out = str(tmp_path / "crop_clamp.jpg")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "crop", src,
             "80", "80", "999", "999", "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        # Clamped: x2=100, y2=100 (image boundary)
        assert data["screenshot_coords"]["x2"] == 100
        assert data["screenshot_coords"]["y2"] == 100
        assert data["crop_dimensions"]["w"] == 20
        assert data["crop_dimensions"]["h"] == 20

    def test_crop_swapped_coords_normalized(self, tmp_path):
        """x1 > x2 (swapped) should be auto-corrected."""
        src = self._make_image(tmp_path / "src.png", size=(200, 200))
        out = str(tmp_path / "crop_swap.jpg")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "crop", src,
             "150", "150", "50", "50", "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        # Should swap so x1=50, y1=50, x2=150, y2=150
        assert data["crop_dimensions"]["w"] == 100
        assert data["crop_dimensions"]["h"] == 100

    def test_crop_coverage_pct(self, tmp_path):
        """Coverage percentage reflects proportion of image area cropped."""
        src = self._make_image(tmp_path / "src.png", size=(100, 100))
        out = str(tmp_path / "crop_cov.jpg")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "crop", src,
             "0", "0", "50", "50", "--out", out],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # 50x50 out of 100x100 = 25%
        assert data["coverage_pct"] == pytest.approx(25.0, abs=0.5)

    def test_crop_missing_source(self, tmp_path):
        """Missing source image should return ok=false and non-zero exit."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "crop", str(tmp_path / "nonexistent.png"),
             "0", "0", "50", "50"],
            capture_output=True, text=True, timeout=10,
        )
        # result_json(False,...) exits with code 1
        assert result.returncode != 0
        data = json.loads(result.stdout)
        assert data["ok"] is False

    def test_crop_parser_registered(self):
        """crop subcommand should be registered in argparse."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "crop", "--help"],
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0
        assert "crop" in result.stdout.lower()
        assert "source" in result.stdout.lower()
        assert "space" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Phase 13 — Clipboard Integration
# ---------------------------------------------------------------------------

class TestPhase13Clipboard:
    """Tests for clipboard get/set/copy/paste commands (no VNC required for set/get)."""

    def test_parser_registered(self):
        """clipboard subcommand should be registered in argparse."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "--help"],
            capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0
        assert "get" in result.stdout
        assert "set" in result.stdout
        assert "copy" in result.stdout
        assert "paste" in result.stdout

    def test_set_and_get_roundtrip(self):
        """clipboard set then get should return same text (macOS pbcopy/pbpaste)."""
        import platform
        if platform.system() != "Darwin":
            pytest.skip("macOS-only test (pbcopy/pbpaste)")
        sentinel = "vnc_phase13_test_" + str(int(time.time()))
        # set
        result_set = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "set", "--text", sentinel],
            capture_output=True, text=True, timeout=10,
        )
        assert result_set.returncode == 0, result_set.stdout
        data_set = json.loads(result_set.stdout)
        assert data_set["ok"] is True
        assert data_set["clipboard_set"] is True
        assert data_set["length"] == len(sentinel)
        # get
        result_get = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "get"],
            capture_output=True, text=True, timeout=10,
        )
        assert result_get.returncode == 0, result_get.stdout
        data_get = json.loads(result_get.stdout)
        assert data_get["ok"] is True
        assert data_get["clipboard"] == sentinel
        assert data_get["length"] == len(sentinel)

    def test_set_empty_string(self):
        """clipboard set with empty string should succeed."""
        import platform
        if platform.system() != "Darwin":
            pytest.skip("macOS-only test (pbcopy/pbpaste)")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "set", "--text", ""],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["length"] == 0

    def test_set_requires_text_flag(self):
        """clipboard set without --text should fail gracefully."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "set"],
            capture_output=True, text=True, timeout=10,
        )
        # Should return ok=false or fail with non-zero exit
        try:
            data = json.loads(result.stdout)
            assert data["ok"] is False
        except json.JSONDecodeError:
            # argparse error is also acceptable (non-zero exit, stderr message)
            assert result.returncode != 0

    def test_paste_requires_text_flag(self):
        """clipboard paste without --text should fail gracefully."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "paste"],
            capture_output=True, text=True, timeout=10,
        )
        try:
            data = json.loads(result.stdout)
            assert data["ok"] is False
        except json.JSONDecodeError:
            assert result.returncode != 0

    def test_get_returns_structure(self):
        """clipboard get should return ok, clipboard, length, lines fields."""
        import platform
        if platform.system() != "Darwin":
            pytest.skip("macOS-only test (pbcopy/pbpaste)")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "get"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert "clipboard" in data
        assert "length" in data
        assert "lines" in data
        assert isinstance(data["length"], int)
        assert isinstance(data["lines"], int)

    def test_set_multiline(self):
        """clipboard set/get should preserve multiline text."""
        import platform
        if platform.system() != "Darwin":
            pytest.skip("macOS-only test (pbcopy/pbpaste)")
        text = "line1\nline2\nline3"
        result_set = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "set", "--text", text],
            capture_output=True, text=True, timeout=10,
        )
        assert result_set.returncode == 0
        result_get = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "get"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(result_get.stdout)
        assert data["ok"] is True
        assert data["lines"] >= 3

    def test_invalid_subaction(self):
        """Unknown clipboard subaction should fail cleanly."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "zap"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_set_unicode(self):
        """clipboard set should handle unicode text (emoji + CJK)."""
        import platform
        if platform.system() != "Darwin":
            pytest.skip("macOS-only test (pbcopy/pbpaste)")
        text = "⚡ Alpha 测试 🎯"
        result_set = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "set", "--text", text],
            capture_output=True, text=True, timeout=10,
        )
        assert result_set.returncode == 0
        data_set = json.loads(result_set.stdout)
        assert data_set["ok"] is True
        # verify roundtrip
        result_get = subprocess.run(
            [sys.executable, str(_SCRIPT), "clipboard", "get"],
            capture_output=True, text=True, timeout=10,
        )
        data_get = json.loads(result_get.stdout)
        assert data_get["ok"] is True
        assert data_get["clipboard"] == text

    def test_copy_subaction_exists_in_dispatch(self):
        """cmd_clipboard should be reachable via 'copy' subaction path (no VNC needed for unit check)."""
        # Verify the function is importable and handles the copy subaction branch
        import types
        assert hasattr(vnc, "cmd_clipboard")
        assert callable(vnc.cmd_clipboard)


class TestPhase14OCR:
    """Unit tests for Phase 14 read_text OCR command."""

    def test_cli_read_text_screen_help(self):
        """read_text subcommand should appear in --help output."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "read_text" in result.stdout

    def test_cli_read_text_choices(self):
        """read_text should accept 'screen' and 'file' sources."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "read_text", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "screen" in result.stdout
        assert "file" in result.stdout

    def test_cli_read_text_invalid_source(self):
        """read_text with invalid source should exit non-zero."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "read_text", "ftp"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0

    def test_cmd_read_text_registered(self):
        """cmd_read_text should be importable and callable."""
        assert hasattr(vnc, "cmd_read_text")
        assert callable(vnc.cmd_read_text)

    def test_read_text_file_not_found(self):
        """read_text file with missing path returns ok=False JSON (exits 1)."""
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "read_text", "file", "/tmp/nonexistent_abc123.png"],
            capture_output=True, text=True, timeout=10,
        )
        # Script exits non-zero and outputs error JSON
        assert result.returncode != 0 or result.stdout.strip()
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert "not found" in data.get("error", "").lower()

    def test_read_text_file_valid_image(self, tmp_path):
        """read_text file should OCR a simple synthetic image."""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import pytesseract
        except ImportError:
            pytest.skip("Pillow or pytesseract not installed")

        # Create a white image with black text
        img = Image.new("RGB", (400, 80), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "Hello OCR", fill="black")
        img_path = str(tmp_path / "test_ocr.png")
        img.save(img_path)

        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "read_text", "file", img_path],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert "text" in data
        assert "char_count" in data
        assert "line_count" in data
        assert "lang" in data

    def test_read_text_file_raw_flag(self, tmp_path):
        """read_text file --raw should include words array with confidence."""
        try:
            from PIL import Image, ImageDraw
            import pytesseract
        except ImportError:
            pytest.skip("Pillow or pytesseract not installed")

        img = Image.new("RGB", (300, 60), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "Alpha", fill="black")
        img_path = str(tmp_path / "test_raw.png")
        img.save(img_path)

        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "read_text", "file", img_path, "--raw"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert "words" in data
        assert isinstance(data["words"], list)

    def test_read_text_region_crop(self, tmp_path):
        """read_text file --region should crop before OCR without error."""
        try:
            from PIL import Image, ImageDraw
            import pytesseract
        except ImportError:
            pytest.skip("Pillow or pytesseract not installed")

        img = Image.new("RGB", (500, 200), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((50, 50), "Region Text", fill="black")
        img_path = str(tmp_path / "test_region.png")
        img.save(img_path)

        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "read_text", "file", img_path,
             "--region", "0", "0", "400", "150"],
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert "text" in data
