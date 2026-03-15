#!/usr/bin/env python3
"""
vnc-control — Visual bridge for AI agents to control remote desktops via VNC.

Usage:
    vnc-control screenshot [--out FILE]
    vnc-control click X Y [--button left|right|middle] [--double]
    vnc-control move X Y
    vnc-control type TEXT
    vnc-control key KEY
    vnc-control connect
    vnc-control status

Connection via args (--host, --port, --password, --username) or env
(VNC_HOST, VNC_PORT, VNC_PASSWORD, VNC_USERNAME). Args override env.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def get_connection_config(args):
    """Resolve connection config from args + env. Args win."""
    return {
        "host": getattr(args, "host", None) or os.environ.get("VNC_HOST", "127.0.0.1"),
        "port": getattr(args, "port", None) or os.environ.get("VNC_PORT", "5900"),
        "password": getattr(args, "password", None) or os.environ.get("VNC_PASSWORD", ""),
        "username": getattr(args, "username", None) or os.environ.get("VNC_USERNAME", ""),
    }


def build_vncdo_base(config):
    """Build the base vncdo command with connection args."""
    cmd = [
        "vncdo",
        "-s", f"{config['host']}::{config['port']}",
        "-t", "15",
    ]
    if config["password"]:
        cmd += ["-p", config["password"]]
    if config["username"]:
        cmd += ["-u", config["username"]]
    return cmd


def run_vncdo(config, actions, capture_path=None):
    """Run vncdo with given actions. Returns (success, stdout, stderr, duration)."""
    cmd = build_vncdo_base(config)
    cmd += actions

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    duration = round(time.time() - start, 2)

    return result.returncode == 0, result.stdout, result.stderr, duration


def result_json(ok, data=None, error=None):
    """Print result as JSON and exit."""
    out = {"ok": ok}
    if data:
        out.update(data)
    if error:
        out["error"] = error
    print(json.dumps(out, indent=2))
    sys.exit(0 if ok else 1)


def get_image_info(path):
    """Get basic image dimensions using PIL if available, else just file size."""
    info = {"path": str(path), "size_bytes": os.path.getsize(path)}
    try:
        from PIL import Image
        img = Image.open(path)
        info["width"] = img.width
        info["height"] = img.height
        img.close()
    except Exception:
        pass
    return info


def cmd_screenshot(args, config):
    """Capture a screenshot."""
    out_path = args.out
    if not out_path:
        ts = int(time.time())
        out_dir = Path(tempfile.gettempdir()) / "vnc-control"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / f"screenshot-{ts}.png")
    else:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    actions = ["--nocursor", "capture", out_path] if args.no_cursor else ["capture", out_path]

    ok, stdout, stderr, duration = run_vncdo(config, actions)
    if ok and os.path.exists(out_path):
        img_info = get_image_info(out_path)
        result_json(True, {
            "action": "screenshot",
            "image": img_info,
            "duration_s": duration,
        })
    else:
        result_json(False, error=f"Screenshot failed: {stderr.strip()}")


def cmd_click(args, config):
    """Click at x,y coordinates."""
    x, y = args.x, args.y
    button_map = {"left": "1", "right": "3", "middle": "2"}
    button = button_map.get(args.button, "1")

    actions = ["move", str(x), str(y), "click", button]
    if args.double:
        actions += ["click", button]

    # Take a screenshot after clicking to verify
    ts = int(time.time())
    out_dir = Path(tempfile.gettempdir()) / "vnc-control"
    out_dir.mkdir(exist_ok=True)
    verify_path = str(out_dir / f"after-click-{ts}.png")
    actions += ["pause", "0.3", "capture", verify_path]

    ok, stdout, stderr, duration = run_vncdo(config, actions)
    if ok:
        data = {
            "action": "click",
            "x": x, "y": y,
            "button": args.button,
            "double": args.double,
            "duration_s": duration,
        }
        if os.path.exists(verify_path):
            data["verify_image"] = get_image_info(verify_path)
        result_json(True, data)
    else:
        result_json(False, error=f"Click failed: {stderr.strip()}")


def cmd_move(args, config):
    """Move pointer to x,y."""
    # Flush with a throwaway capture for reliable completion on macOS ARD
    tmp_capture = str(Path(tempfile.gettempdir()) / "vnc-control" / ".move-flush.png")
    Path(tmp_capture).parent.mkdir(parents=True, exist_ok=True)
    actions = ["move", str(args.x), str(args.y), "capture", tmp_capture]

    ok, stdout, stderr, duration = run_vncdo(config, actions)
    try:
        if os.path.exists(tmp_capture):
            os.unlink(tmp_capture)
    except OSError:
        pass

    if ok:
        result_json(True, {
            "action": "move",
            "x": args.x, "y": args.y,
            "duration_s": duration,
        })
    else:
        result_json(False, error=f"Move failed: {stderr.strip()}")


def cmd_type(args, config):
    """Type text."""
    actions = ["type", args.text]

    ok, stdout, stderr, duration = run_vncdo(config, actions)
    if ok:
        result_json(True, {
            "action": "type",
            "text_length": len(args.text),
            "duration_s": duration,
        })
    else:
        result_json(False, error=f"Type failed: {stderr.strip()}")


def cmd_key(args, config):
    """Send a key press."""
    # Append a throwaway capture after key events — vncdotool hangs waiting
    # for a framebuffer update after bare key presses on macOS ARD.
    # The capture forces a framebuffer request that completes the loop.
    tmp_capture = str(Path(tempfile.gettempdir()) / "vnc-control" / ".key-flush.png")
    Path(tmp_capture).parent.mkdir(parents=True, exist_ok=True)
    actions = ["key", args.key, "capture", tmp_capture]

    ok, stdout, stderr, duration = run_vncdo(config, actions)
    # Clean up throwaway capture
    try:
        if os.path.exists(tmp_capture):
            os.unlink(tmp_capture)
    except OSError:
        pass

    if ok:
        result_json(True, {
            "action": "key",
            "key": args.key,
            "duration_s": duration,
        })
    else:
        result_json(False, error=f"Key failed: {stderr.strip()}")


def cmd_connect(args, config):
    """Test connection by capturing and discarding a screenshot."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as f:
        tmp_path = f.name

    actions = ["capture", tmp_path]
    ok, stdout, stderr, duration = run_vncdo(config, actions)

    if ok and os.path.exists(tmp_path):
        try:
            from PIL import Image
            img = Image.open(tmp_path)
            w, h = img.width, img.height
            img.close()
        except Exception:
            w, h = None, None
        os.unlink(tmp_path)
        result_json(True, {
            "action": "connect",
            "host": config["host"],
            "port": config["port"],
            "screen_width": w,
            "screen_height": h,
            "duration_s": duration,
        })
    else:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        result_json(False, error=f"Connection failed: {stderr.strip()}")


def cmd_status(args, config):
    """Check if VNC host is reachable."""
    import socket
    host = config["host"]
    port = int(config["port"])

    try:
        sock = socket.create_connection((host, port), timeout=5)
        banner = sock.recv(32).decode("utf-8", errors="replace").strip()
        sock.close()
        result_json(True, {
            "action": "status",
            "host": host,
            "port": port,
            "reachable": True,
            "banner": banner,
        })
    except Exception as e:
        result_json(False, error=f"Host unreachable: {e}")


def main():
    parser = argparse.ArgumentParser(
        prog="vnc-control",
        description="Visual bridge for AI agents to control remote desktops via VNC.",
    )

    # Global connection args
    parser.add_argument("--host", help="VNC host (default: $VNC_HOST or 127.0.0.1)")
    parser.add_argument("--port", help="VNC port (default: $VNC_PORT or 5900)")
    parser.add_argument("--password", help="VNC password (default: $VNC_PASSWORD)")
    parser.add_argument("--username", help="VNC/ARD username (default: $VNC_USERNAME)")

    sub = parser.add_subparsers(dest="command", required=True)

    # screenshot
    p_ss = sub.add_parser("screenshot", help="Capture screenshot")
    p_ss.add_argument("--out", help="Output file path (default: auto-generated)")
    p_ss.add_argument("--no-cursor", action="store_true", help="Hide cursor in capture")

    # click
    p_click = sub.add_parser("click", help="Click at coordinates")
    p_click.add_argument("x", type=int)
    p_click.add_argument("y", type=int)
    p_click.add_argument("--button", default="left", choices=["left", "right", "middle"])
    p_click.add_argument("--double", action="store_true")

    # move
    p_move = sub.add_parser("move", help="Move pointer to coordinates")
    p_move.add_argument("x", type=int)
    p_move.add_argument("y", type=int)

    # type
    p_type = sub.add_parser("type", help="Type text")
    p_type.add_argument("text")

    # key
    p_key = sub.add_parser("key", help="Send key press (e.g., enter, tab, ctrl-c)")
    p_key.add_argument("key")

    # connect
    sub.add_parser("connect", help="Test VNC connection")

    # status
    sub.add_parser("status", help="Check if VNC host is reachable")

    args = parser.parse_args()
    config = get_connection_config(args)

    commands = {
        "screenshot": cmd_screenshot,
        "click": cmd_click,
        "move": cmd_move,
        "type": cmd_type,
        "key": cmd_key,
        "connect": cmd_connect,
        "status": cmd_status,
    }

    commands[args.command](args, config)


if __name__ == "__main__":
    main()
