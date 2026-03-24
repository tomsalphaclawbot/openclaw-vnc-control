"""
Unit tests for Phase 6 multi-session support.

Tests cover:
- sessions.json loading + resolve_session()
- --session flag in get_config()
- /sessions/* API endpoints
- Session-scoped routes (/sessions/{name}/status, etc.)
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import vnc_api  # noqa: E402
from vnc_api import app  # noqa: E402
from fastapi.testclient import TestClient


# ─── Helpers ─────────────────────────────────────────────────────────────────

SAMPLE_SESSIONS = {
    "default": "local",
    "sessions": {
        "local": {"host": "127.0.0.1", "port": "5900", "username": "admin", "password": "secret"},
        "office": {"host": "192.168.1.100", "port": "5900", "username": "user", "password": ""},
        "pi": {"host": "raspberrypi.local", "port": "5901", "username": "pi", "password": ""},
    },
}


def _load_vnc_control() -> ModuleType:
    """Load vnc-control.py (hyphenated) as a module via importlib."""
    spec = importlib.util.spec_from_file_location(
        "vnc_control", PROJECT_ROOT / "vnc-control.py"
    )
    mod = importlib.util.module_from_spec(spec)
    # Suppress argparse/main execution on import
    with patch("sys.argv", ["vnc-control"]):
        try:
            spec.loader.exec_module(mod)
        except SystemExit:
            pass
    return mod


@pytest.fixture(scope="session")
def vcm():
    """Load vnc-control module once per test session."""
    return _load_vnc_control()


@pytest.fixture()
def client():
    vnc_api.API_SECRET = ""
    return TestClient(app)


@pytest.fixture()
def sessions_file(tmp_path):
    """Write a sessions.json to a temp path and return it."""
    p = tmp_path / "sessions.json"
    p.write_text(json.dumps(SAMPLE_SESSIONS))
    return p


# ─── vnc-control.py unit tests ───────────────────────────────────────────────

class TestLoadSessionsConfig:
    def test_no_file_returns_empty(self, vcm, tmp_path, monkeypatch):
        monkeypatch.setattr(vcm, "SESSIONS_FILE", tmp_path / "nonexistent.json")
        cfg = vcm.load_sessions_config()
        assert cfg["sessions"] == {}
        assert cfg["default"] is None

    def test_loads_sessions(self, vcm, sessions_file, monkeypatch):
        monkeypatch.setattr(vcm, "SESSIONS_FILE", sessions_file)
        cfg = vcm.load_sessions_config()
        assert set(cfg["sessions"].keys()) == {"local", "office", "pi"}
        assert cfg["default"] == "local"

    def test_resolve_named_session(self, vcm, sessions_file, monkeypatch):
        monkeypatch.setattr(vcm, "SESSIONS_FILE", sessions_file)
        s = vcm.resolve_session("office")
        assert s["host"] == "192.168.1.100"
        assert s["port"] == "5900"

    def test_resolve_nonexistent_returns_none(self, vcm, sessions_file, monkeypatch):
        monkeypatch.setattr(vcm, "SESSIONS_FILE", sessions_file)
        assert vcm.resolve_session("doesnotexist") is None

    def test_resolve_none_returns_default_session(self, vcm, sessions_file, monkeypatch):
        """resolve_session(None) auto-resolves to the configured default session.
        get_config() guards against unintended default resolution via 'if session_name' check."""
        monkeypatch.setattr(vcm, "SESSIONS_FILE", sessions_file)
        s = vcm.resolve_session(None)
        # SAMPLE_SESSIONS has default="local"
        assert s is not None
        assert s["host"] == "127.0.0.1"

    def test_list_sessions(self, vcm, sessions_file, monkeypatch):
        monkeypatch.setattr(vcm, "SESSIONS_FILE", sessions_file)
        names, default = vcm.list_sessions()
        assert set(names) == {"local", "office", "pi"}
        assert default == "local"


# ─── API endpoint tests ───────────────────────────────────────────────────────

class TestSessionsEndpoints:
    def test_list_sessions_endpoint(self, client):
        with patch("vnc_api._run", return_value={"ok": True, "sessions": ["local", "office"], "default": "local", "count": 2}):
            resp = client.get("/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "sessions" in data

    def test_show_session_endpoint(self, client):
        with patch("vnc_api._run", return_value={"ok": True, "session": "office", "config": {"host": "192.168.1.100"}, "default": False}):
            resp = client.get("/sessions/office")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["session"] == "office"

    def test_session_status_endpoint(self, client):
        with patch("vnc_api._run", return_value={"ok": True, "action": "status", "host": "192.168.1.100"}):
            resp = client.get("/sessions/office/status")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_session_screenshot_endpoint(self, client, tmp_path):
        fake_img = tmp_path / "test.jpeg"
        fake_img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)  # fake JPEG bytes

        def fake_run(args, timeout=20):
            return {"ok": True, "path": str(fake_img)}

        with patch("vnc_api._run", side_effect=fake_run):
            resp = client.post("/sessions/local/screenshot", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "image_b64" in data

    def test_session_click_endpoint(self, client):
        with patch("vnc_api._run", return_value={"ok": True}):
            resp = client.post("/sessions/local/click", json={"x": 100, "y": 200})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_session_type_endpoint(self, client):
        with patch("vnc_api._run", return_value={"ok": True}):
            resp = client.post("/sessions/local/type", json={"text": "hello world"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_session_key_endpoint(self, client):
        with patch("vnc_api._run", return_value={"ok": True}):
            resp = client.post("/sessions/local/key", json={"keys": ["ctrl", "c"]})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_session_args_injected(self, client):
        """Verify --session flag is passed to _run for session-scoped routes."""
        captured = {}

        def fake_run(args, timeout=20):
            captured["args"] = args
            return {"ok": True}

        with patch("vnc_api._run", side_effect=fake_run):
            client.post("/sessions/pi/key", json={"keys": ["enter"]})

        assert "--session" in captured["args"]
        assert "pi" in captured["args"]

    def test_session_args_empty_for_default_routes(self, client):
        """Non-session routes do NOT inject --session."""
        captured = {}

        def fake_run(args, timeout=20):
            captured["args"] = args
            return {"ok": True}

        with patch("vnc_api._run", side_effect=fake_run):
            client.post("/key", json={"keys": ["enter"]})

        assert "--session" not in captured.get("args", [])
