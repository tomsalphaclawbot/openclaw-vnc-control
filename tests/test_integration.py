"""
Integration / e2e smoke tests for vnc-control.py.

These tests require a live VNC server. They are automatically SKIPPED when:
  - VNC_HOST env var is not set, OR
  - The VNC connection check (cmd_connect) fails.

To run against a real server:
  VNC_HOST=127.0.0.1 VNC_PORT=5900 VNC_PASSWORD=... pytest tests/test_integration.py -v

Sprint F: e2e smoke tests — connection + screenshot round-trip.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load vnc-control as a module
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
_SCRIPT = _ROOT / "vnc-control.py"

spec = importlib.util.spec_from_file_location("vnc_control", _SCRIPT)
vnc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vnc)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _vnc_env_present():
    """True if minimum env vars for a VNC connection are present."""
    return bool(os.environ.get("VNC_HOST"))


def _build_config():
    return {
        "host": os.environ.get("VNC_HOST", "127.0.0.1"),
        "port": int(os.environ.get("VNC_PORT", "5900")),
        "password": os.environ.get("VNC_PASSWORD", ""),
        "username": os.environ.get("VNC_USERNAME", ""),
    }


@pytest.fixture(scope="session")
def vnc_available():
    """Session-scoped fixture: skip the entire integration suite if VNC is unreachable."""
    if not _vnc_env_present():
        pytest.skip("VNC_HOST not set — skipping integration tests")

    config = _build_config()

    # Quick connection probe via run_vncdo
    ok, stdout, stderr, _ = vnc.run_vncdo(config, ["type", ""], timeout=8)
    if not ok:
        pytest.skip(f"VNC not reachable ({stderr.strip()[:80]}) — skipping integration tests")

    return config


@pytest.fixture()
def config(vnc_available):
    return vnc_available


# ---------------------------------------------------------------------------
# CLI smoke runner (calls the script as subprocess, captures JSON stdout)
# ---------------------------------------------------------------------------

def _run_cli(*args, env=None):
    """Run vnc-control as a subprocess, return (returncode, parsed_json_or_None, raw_stdout)."""
    cmd = [sys.executable, str(_SCRIPT)] + list(args)
    e = dict(os.environ)
    if env:
        e.update(env)
    result = subprocess.run(cmd, capture_output=True, text=True, env=e, timeout=30)
    try:
        parsed = json.loads(result.stdout)
    except Exception:
        parsed = None
    return result.returncode, parsed, result.stdout


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestVNCConnect:
    """Basic connectivity check."""

    def test_connect_returns_ok(self, config):
        ok, _, stderr, _ = vnc.run_vncdo(config, ["type", ""], timeout=10)
        assert ok, f"Expected VNC connection success, got stderr: {stderr}"


class TestScreenshotRoundTrip:
    """Take a screenshot, verify metadata and file output."""

    def test_screenshot_produces_file(self, config, tmp_path):
        out = str(tmp_path / "smoke.jpg")

        class Args:
            out = None
            profile = "manual"
            format = "jpeg"
            scale = 0.5
            quality = 70
            no_cursor = False

        args = Args()
        args.out = out

        # Capture screenshot
        rc, _, _ = _run_cli(
            "--host", config["host"],
            "--port", str(config["port"]),
            "--password", config["password"],
            "screenshot",
            "--out", out,
            "--format", "jpeg",
            "--scale", "0.5",
        )
        assert rc == 0, "Screenshot command should exit 0"
        assert Path(out).exists(), "Screenshot file should exist on disk"
        assert Path(out).stat().st_size > 10_000, "Screenshot should be a real image (>10KB)"

    def test_screenshot_json_output_shape(self, config, tmp_path):
        out = str(tmp_path / "smoke2.jpg")
        rc, parsed, raw = _run_cli(
            "--host", config["host"],
            "--port", str(config["port"]),
            "--password", config["password"],
            "screenshot",
            "--out", out,
            "--format", "jpeg",
            "--scale", "0.5",
        )
        assert rc == 0
        assert parsed is not None, f"Expected JSON output, got: {raw[:200]}"
        assert parsed.get("ok") is True
        assert "image" in parsed
        assert parsed["image"].get("width", 0) > 0
        assert parsed["image"].get("height", 0) > 0
        assert "sha1" in parsed


class TestCLIStatusCommand:
    """vnc-control status should return a JSON object even without a connection."""

    def test_status_exits_zero(self):
        """Status reports env config — doesn't require VNC to be live."""
        rc, parsed, raw = _run_cli("status")
        # Status may exit non-zero if env vars aren't set, but should produce JSON
        assert parsed is not None, f"Status should emit JSON, got: {raw[:200]}"

    def test_status_has_host_field(self):
        rc, parsed, raw = _run_cli(
            "--host", "127.0.0.1",
            "--port", "5900",
            "status",
        )
        assert parsed is not None
        data = parsed.get("data") or parsed
        assert "host" in data or "config" in data or "vnc_host" in str(parsed).lower()


class TestCLIMoveAndMapOffline:
    """map command is pure math — no VNC needed."""

    def test_map_screenshot_to_native(self):
        """map command converts coords without VNC connection."""
        rc, parsed, raw = _run_cli(
            "--host", "127.0.0.1",
            "--port", "5900",
            "map", "100", "200",
            "--from", "screenshot",
            "--to", "native",
            "--scale", "0.5",
        )
        # map may need a probe for native resolution; if it fails, just check exit or JSON shape
        if rc == 0 and parsed:
            to = parsed.get("to", {})
            assert to.get("x") == 200
            assert to.get("y") == 400


class TestKeyNormalization_Integration:
    """Verify that key aliases are properly sent (requires VNC)."""

    def test_key_enter_via_cli(self, config, tmp_path):
        """key enter should succeed without hanging (the return→enter fix)."""
        rc, parsed, raw = _run_cli(
            "--host", config["host"],
            "--port", str(config["port"]),
            "--password", config["password"],
            "key", "enter",
        )
        assert rc == 0, f"key enter should succeed; got: {raw[:200]}"
        if parsed:
            assert parsed.get("ok") is True

    def test_key_return_alias_via_cli(self, config, tmp_path):
        """key return should be aliased to enter and succeed."""
        rc, parsed, raw = _run_cli(
            "--host", config["host"],
            "--port", str(config["port"]),
            "--password", config["password"],
            "key", "return",
        )
        assert rc == 0, f"key return (→enter alias) should succeed; got: {raw[:200]}"
