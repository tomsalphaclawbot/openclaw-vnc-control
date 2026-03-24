#!/usr/bin/env python3
"""
vnc-api.py — HTTP API wrapper for vnc-control.

Exposes all core VNC bridge operations as JSON HTTP endpoints, making the VNC
bridge consumable by multi-agent systems and remote orchestrators without
requiring direct subprocess calls.

Usage:
    ./vnc-api.py [--port 7472] [--bind 127.0.0.1] [--secret TOKEN]
    uvicorn vnc-api:app --host 127.0.0.1 --port 7472

Auth:
    Optional shared secret via --secret or VNC_API_SECRET env var.
    When set, all requests must include: X-VNC-API-Secret: <token>

Endpoints:
    GET  /status                  — Connection + server status
    POST /screenshot              — Capture screenshot, returns base64 image
    POST /click                   — Click at (x, y) in given coordinate space
    POST /move                    — Move pointer to (x, y)
    POST /type                    — Type text
    POST /key                     — Send key(s)

All responses are JSON with shape: {"ok": bool, ...payload}

Environment (same as vnc-control.py):
    VNC_HOST, VNC_PORT, VNC_PASSWORD, VNC_USERNAME
    VNC_API_SECRET  — shared-secret auth token (optional)
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ─── Config ───────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent
VNC_CONTROL = HERE / "vnc-control.py"
VENV_PYTHON = HERE / ".venv" / "bin" / "python3"
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

API_SECRET = os.environ.get("VNC_API_SECRET", "")

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="vnc-control HTTP API",
    description="HTTP bridge for VNC automation via vnc-control.py",
    version="0.2.0",
)

# ─── Auth middleware ──────────────────────────────────────────────────────────

@app.middleware("http")
async def check_secret(request: Request, call_next):
    if API_SECRET:
        token = request.headers.get("X-VNC-API-Secret", "")
        if token != API_SECRET:
            return JSONResponse(
                status_code=401,
                content={"ok": False, "error": "Unauthorized: invalid or missing X-VNC-API-Secret"},
            )
    return await call_next(request)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _vnc_env():
    """Return env dict for subprocess calls (passes VNC_* vars through)."""
    env = os.environ.copy()
    # Ensure .env is loaded by subprocess via vnc-control.py's own loader
    return env


def _run(args: List[str], timeout: int = 20) -> dict:
    """Run vnc-control.py with given args, parse JSON output."""
    cmd = [PYTHON, str(VNC_CONTROL)] + args
    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_vnc_env(),
            cwd=str(HERE),
        )
        duration = round(time.time() - start, 2)
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if stdout:
            try:
                result = json.loads(stdout)
                result.setdefault("duration_s", duration)
                return result
            except json.JSONDecodeError:
                pass

        # Non-JSON output — treat as raw text
        ok = proc.returncode == 0
        return {
            "ok": ok,
            "stdout": stdout,
            "stderr": stderr,
            "duration_s": duration,
        }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Subprocess timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ─── Models ──────────────────────────────────────────────────────────────────

class ClickRequest(BaseModel):
    x: float
    y: float
    space: Optional[str] = "screenshot"  # screenshot | native | normalized

class MoveRequest(BaseModel):
    x: float
    y: float
    space: Optional[str] = "screenshot"

class TypeRequest(BaseModel):
    text: str

class KeyRequest(BaseModel):
    keys: List[str]  # e.g. ["ctrl", "c"] or ["enter"]

class ScreenshotRequest(BaseModel):
    format: Optional[str] = "jpeg"
    scale: Optional[float] = 0.5
    quality: Optional[int] = 70
    out: Optional[str] = None  # optional filesystem path; if omitted, returns base64

# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/status")
async def status():
    """Check VNC connection and server health."""
    result = _run(["status"])
    return result


@app.post("/screenshot")
async def screenshot(req: ScreenshotRequest = ScreenshotRequest()):
    """
    Capture a screenshot.

    Returns base64-encoded image data in the `image_b64` field unless
    `out` is provided (in which case the file is written to disk and the
    path is returned).
    """
    import tempfile

    use_tmp = req.out is None
    out_path = req.out or str(Path(tempfile.mktemp(suffix=f".{req.format}")))

    args = [
        "--profile", "ai",
        "screenshot",
        "--format", req.format,
        "--scale", str(req.scale),
        "--quality", str(req.quality),
        "--out", out_path,
    ]

    result = _run(args, timeout=25)

    if result.get("ok") and use_tmp:
        path = Path(result.get("path", out_path))
        if path.exists():
            raw = path.read_bytes()
            b64 = base64.b64encode(raw).decode()
            result["image_b64"] = b64
            result["image_format"] = req.format
            result["image_size_bytes"] = len(raw)
            try:
                path.unlink()
            except Exception:
                pass

    return result


@app.post("/click")
async def click(req: ClickRequest):
    """Click at (x, y). Default space: screenshot coordinates."""
    args = ["click", str(req.x), str(req.y), "--space", req.space]
    return _run(args)


@app.post("/move")
async def move(req: MoveRequest):
    """Move pointer to (x, y) without clicking."""
    args = ["move", str(req.x), str(req.y), "--space", req.space]
    return _run(args)


@app.post("/type")
async def type_text(req: TypeRequest):
    """Type text via VNC keyboard injection."""
    args = ["type", req.text]
    return _run(args)


@app.post("/key")
async def key(req: KeyRequest):
    """Send one or more key events (e.g. ['ctrl', 'c'] or ['enter'])."""
    args = ["key"] + req.keys
    return _run(args)

# ─── Entrypoint ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="vnc-control HTTP API server")
    parser.add_argument("--port", type=int, default=7472, help="Port to listen on (default: 7472)")
    parser.add_argument("--bind", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--secret", default="", help="Shared-secret auth token (env: VNC_API_SECRET)")
    parsed = parser.parse_args()

    if parsed.secret:
        os.environ["VNC_API_SECRET"] = parsed.secret
        global API_SECRET
        API_SECRET = parsed.secret

    print(f"[vnc-api] starting on {parsed.bind}:{parsed.port}")
    print(f"[vnc-api] auth: {'enabled' if API_SECRET else 'disabled (no secret set)'}")
    print(f"[vnc-api] vnc-control: {VNC_CONTROL}")

    uvicorn.run(app, host=parsed.bind, port=parsed.port, log_level="info")


if __name__ == "__main__":
    main()
