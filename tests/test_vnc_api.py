"""
Unit tests for vnc-api.py HTTP routes.

Tests use FastAPI TestClient — no live VNC connection required.
All vnc-control.py subprocess calls are mocked.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

import vnc_api  # noqa: E402 (imported after sys.path fix)
from vnc_api import app  # noqa: E402


@pytest.fixture()
def client():
    """TestClient with no auth secret."""
    vnc_api.API_SECRET = ""
    return TestClient(app)


@pytest.fixture()
def authed_client():
    """TestClient with API secret set to 'test-secret'."""
    vnc_api.API_SECRET = "test-secret"
    yield TestClient(app)
    vnc_api.API_SECRET = ""  # reset after test


# ─── Auth tests ───────────────────────────────────────────────────────────────

def test_no_auth_required_when_no_secret(client):
    with patch("vnc_api._run", return_value={"ok": True, "status": "connected"}):
        resp = client.get("/status")
    assert resp.status_code == 200


def test_auth_required_when_secret_set(authed_client):
    resp = authed_client.get("/status")
    assert resp.status_code == 401
    assert resp.json()["ok"] is False


def test_auth_passes_with_correct_secret(authed_client):
    with patch("vnc_api._run", return_value={"ok": True, "status": "connected"}):
        resp = authed_client.get(
            "/status", headers={"X-VNC-API-Secret": "test-secret"}
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ─── /status ──────────────────────────────────────────────────────────────────

def test_status_ok(client):
    mock_result = {"ok": True, "host": "127.0.0.1", "port": "5900"}
    with patch("vnc_api._run", return_value=mock_result) as m:
        resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    m.assert_called_once_with(["status"])


# ─── /screenshot ─────────────────────────────────────────────────────────────

def test_screenshot_returns_base64(client, tmp_path):
    fake_image = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # fake JPEG bytes
    fake_out = str(tmp_path / "screen.jpeg")

    def fake_run(args, timeout=20):
        # Write fake image to the path vnc-api will read back
        Path(fake_out).write_bytes(fake_image)
        return {"ok": True, "path": fake_out}

    with patch("vnc_api._run", side_effect=fake_run):
        with patch("tempfile.mktemp", return_value=fake_out):
            resp = client.post("/screenshot", json={})

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "image_b64" in data
    import base64
    decoded = base64.b64decode(data["image_b64"])
    assert decoded == fake_image


def test_screenshot_with_custom_params(client):
    with patch("vnc_api._run", return_value={"ok": True, "path": "/tmp/x.jpeg"}) as m:
        client.post("/screenshot", json={"format": "png", "scale": 1.0, "quality": 90})
    call_args = m.call_args[0][0]
    assert "--format" in call_args
    assert "png" in call_args
    assert "--scale" in call_args
    assert "1.0" in call_args


# ─── /click ──────────────────────────────────────────────────────────────────

def test_click_default_space(client):
    with patch("vnc_api._run", return_value={"ok": True}) as m:
        resp = client.post("/click", json={"x": 100, "y": 200})
    assert resp.status_code == 200
    call_args = m.call_args[0][0]
    assert "click" in call_args
    assert "100.0" in call_args
    assert "200.0" in call_args
    assert "screenshot" in call_args


def test_click_native_space(client):
    with patch("vnc_api._run", return_value={"ok": True}) as m:
        resp = client.post("/click", json={"x": 50, "y": 75, "space": "native"})
    call_args = m.call_args[0][0]
    assert "native" in call_args


# ─── /type ───────────────────────────────────────────────────────────────────

def test_type_text(client):
    with patch("vnc_api._run", return_value={"ok": True}) as m:
        resp = client.post("/type", json={"text": "hello world"})
    assert resp.status_code == 200
    call_args = m.call_args[0][0]
    assert "type" in call_args
    assert "hello world" in call_args


# ─── /key ────────────────────────────────────────────────────────────────────

def test_key_single(client):
    with patch("vnc_api._run", return_value={"ok": True}) as m:
        resp = client.post("/key", json={"keys": ["enter"]})
    assert resp.status_code == 200
    call_args = m.call_args[0][0]
    assert "key" in call_args
    assert "enter" in call_args


def test_key_combo(client):
    with patch("vnc_api._run", return_value={"ok": True}) as m:
        resp = client.post("/key", json={"keys": ["ctrl", "c"]})
    call_args = m.call_args[0][0]
    assert "ctrl" in call_args
    assert "c" in call_args


# ─── /move ───────────────────────────────────────────────────────────────────

def test_move(client):
    with patch("vnc_api._run", return_value={"ok": True}) as m:
        resp = client.post("/move", json={"x": 300, "y": 400})
    assert resp.status_code == 200
    call_args = m.call_args[0][0]
    assert "move" in call_args
    assert "300.0" in call_args


# ─── Error handling ───────────────────────────────────────────────────────────

def test_run_error_propagated(client):
    with patch("vnc_api._run", return_value={"ok": False, "error": "Connection refused"}):
        resp = client.get("/status")
    assert resp.status_code == 200  # HTTP 200, but ok=False in body
    assert resp.json()["ok"] is False
