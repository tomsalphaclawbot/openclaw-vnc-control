#!/usr/bin/env python3
"""
vnc-control - Visual bridge for AI agents to control remote desktops via VNC.

Core design principle: AI vision models analyze screenshots and return coordinates
in SCREENSHOT space. This tool auto-converts to native VNC coordinates.

Usage:
    vnc-control --profile ai screenshot [--out FILE]
    vnc-control click X Y [--space screenshot|native|normalized]
    vnc-control move X Y [--space screenshot|native|normalized]
    vnc-control type TEXT
    vnc-control key KEY [KEY2 ...]
    vnc-control combo ACTION [ACTION ...]
    vnc-control map X Y --from screenshot --to native
    vnc-control connect
    vnc-control status

Coordinate system:
    Default input space is SCREENSHOT coordinates.
    Native translation is performed programmatically.
    Normalized space is supported (0..1 floats relative to native resolution).

Connection via args (--host, --port, --password, --username) or env
(VNC_HOST, VNC_PORT, VNC_PASSWORD, VNC_USERNAME). Args override env.
"""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_SCALE = 0.5
DEFAULT_FORMAT = "jpeg"
DEFAULT_QUALITY = 80
DEFAULT_PROFILE = "manual"
AI_PROFILE_DEFAULTS = {
    "format": "jpeg",
    "scale": 0.5,
    "quality": 70,
}
VNCDO_TIMEOUT = 12  # vncdo internal timeout (seconds)
SUBPROCESS_TIMEOUT = 18  # subprocess kill timeout
NATIVE_WIDTH = None  # auto-detected on first connect
NATIVE_HEIGHT = None
STATE_DIR = Path(tempfile.gettempdir()) / "vnc-control"
STATE_FILE = STATE_DIR / "last_capture.json"

# ─── .env loader ──────────────────────────────────────────────────────────────

def load_dotenv():
    """Load .env from script dir. Simple key=value, no overwrite."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

load_dotenv()

# ─── Connection ───────────────────────────────────────────────────────────────

def get_config(args):
    return {
        "host": getattr(args, "host", None) or os.environ.get("VNC_HOST", "127.0.0.1"),
        "port": getattr(args, "port", None) or os.environ.get("VNC_PORT", "5900"),
        "password": getattr(args, "password", None) or os.environ.get("VNC_PASSWORD", ""),
        "username": getattr(args, "username", None) or os.environ.get("VNC_USERNAME", ""),
    }

def vncdo_base(config):
    cmd = ["vncdo", "-s", f"{config['host']}::{config['port']}", "-t", str(VNCDO_TIMEOUT)]
    if config["password"]:
        cmd += ["-p", config["password"]]
    if config["username"]:
        cmd += ["-u", config["username"]]
    return cmd

def run_vncdo(config, actions, timeout=None, timeout_ok=False):
    """Run vncdo. Returns (ok, stdout, stderr, duration).

    timeout_ok=True: treat timeouts as success (key was sent, framebuffer hung).
    """
    timeout = timeout or SUBPROCESS_TIMEOUT
    cmd = vncdo_base(config) + actions
    start = time.time()

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                preexec_fn=os.setsid)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Kill the entire process group to prevent zombie connections
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=2)
            duration = round(time.time() - start, 2)
            if timeout_ok:
                return True, "", "subprocess_timeout (action sent)", duration
            return False, "", f"TIMEOUT after {timeout}s", duration

        duration = round(time.time() - start, 2)

        if proc.returncode != 0 and timeout_ok:
            stderr_s = stderr.strip()
            if "TIMEOUT" in stderr_s or "Connection" in stderr_s:
                return True, stdout, f"vncdo_timeout (action sent): {stderr_s[-120:]}", duration

        return proc.returncode == 0, stdout, stderr, duration

    except Exception as e:
        duration = round(time.time() - start, 2)
        return False, "", str(e), duration

# ─── Output helpers ───────────────────────────────────────────────────────────

def result_json(ok, data=None, error=None):
    out = {"ok": ok}
    if data:
        out.update(data)
    if error:
        out["error"] = error
    print(json.dumps(out, indent=2))
    sys.exit(0 if ok else 1)

def get_image_info(path):
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


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def load_last_capture_state():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return None


def save_last_capture_state(data):
    try:
        tmpdir()
        STATE_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def infer_screenshot_scale(arg_scale):
    if arg_scale is not None:
        return arg_scale
    state = load_last_capture_state()
    if state and state.get("scale"):
        return float(state["scale"])
    return DEFAULT_SCALE


def get_profile(args):
    return getattr(args, "profile", None) or os.environ.get("VNC_PROFILE", DEFAULT_PROFILE)


def normalize_key_name(key: str) -> str:
    """Normalize key aliases for better macOS ARD compatibility.

    Empirical finding: `vncdo key Return` frequently times out/hangs against macOS ARD,
    while `vncdo key enter` succeeds reliably.
    """
    k = key.strip()
    aliases = {
        "return": "enter",
        "kp_enter": "enter",
        "iso_enter": "enter",
        "linefeed": "enter",
    }
    return aliases.get(k.lower(), k)


def capture_settings(args, prefer_last_scale=False):
    """Resolve capture format/scale/quality from profile + args.

    AI profile is intentionally constrained to efficient capture defaults to avoid
    oversized screenshots in agent loops.
    """
    profile = get_profile(args)

    fmt = getattr(args, "format", None)
    scale = getattr(args, "scale", None)
    quality = getattr(args, "quality", None)

    if fmt is None:
        fmt = AI_PROFILE_DEFAULTS["format"] if profile == "ai" else DEFAULT_FORMAT
    if scale is None:
        if profile == "ai":
            scale = AI_PROFILE_DEFAULTS["scale"]
        elif prefer_last_scale:
            scale = infer_screenshot_scale(None)
        else:
            scale = DEFAULT_SCALE
    if quality is None:
        quality = AI_PROFILE_DEFAULTS["quality"] if profile == "ai" else DEFAULT_QUALITY

    # Hard efficiency guardrails for AI profile
    if profile == "ai":
        if fmt == "png":
            fmt = "jpeg"
        if scale <= 0 or scale > 0.6:
            scale = AI_PROFILE_DEFAULTS["scale"]
        if quality < 40:
            quality = 40
        if quality > 85:
            quality = 85

    return profile, fmt, scale, quality

# ─── Coordinate conversion ────────────────────────────────────────────────────

def detect_native_resolution(config):
    """Capture a tiny screenshot to learn native resolution."""
    global NATIVE_WIDTH, NATIVE_HEIGHT
    if NATIVE_WIDTH and NATIVE_HEIGHT:
        return NATIVE_WIDTH, NATIVE_HEIGHT

    tmp = str(Path(tempfile.gettempdir()) / "vnc-control" / ".probe.png")
    Path(tmp).parent.mkdir(parents=True, exist_ok=True)

    ok, _, stderr, _ = run_vncdo(config, ["capture", tmp], timeout=15)
    if ok and os.path.exists(tmp):
        try:
            from PIL import Image
            img = Image.open(tmp)
            NATIVE_WIDTH, NATIVE_HEIGHT = img.width, img.height
            img.close()
        except Exception:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass

    return NATIVE_WIDTH, NATIVE_HEIGHT

def to_native(x, y, scale):
    """Convert screenshot-space coords to native VNC coords."""
    native_x = int(round(x / scale))
    native_y = int(round(y / scale))
    return native_x, native_y


def from_native(nx, ny, scale):
    """Convert native coords to screenshot-space coords."""
    sx = int(round(nx * scale))
    sy = int(round(ny * scale))
    return sx, sy


def resolve_native_coords(x, y, space, config, scale=None):
    """Resolve input coords from screenshot/native/normalized space to native."""
    native_w, native_h = detect_native_resolution(config)
    if not native_w or not native_h:
        native_w, native_h = 3420, 2214  # fallback for this host

    if space == "native":
        nx, ny = int(round(x)), int(round(y))
        used_scale = None
    elif space == "normalized":
        nx = int(round(float(x) * native_w))
        ny = int(round(float(y) * native_h))
        used_scale = None
    else:
        used_scale = infer_screenshot_scale(scale)
        nx, ny = to_native(float(x), float(y), used_scale)

    return nx, ny, native_w, native_h, used_scale


def convert_between_spaces(x, y, from_space, to_space, config, scale=None):
    """Convert coordinates across screenshot/native/normalized spaces."""
    nx, ny, native_w, native_h, used_scale = resolve_native_coords(x, y, from_space, config, scale=scale)

    if to_space == "native":
        ox, oy = nx, ny
    elif to_space == "normalized":
        ox = round(nx / native_w, 6) if native_w else None
        oy = round(ny / native_h, 6) if native_h else None
    else:
        s = infer_screenshot_scale(scale)
        ox, oy = from_native(nx, ny, s)

    return {
        "from": {"space": from_space, "x": x, "y": y},
        "native": {"x": nx, "y": ny},
        "to": {"space": to_space, "x": ox, "y": oy},
        "native_resolution": {"w": native_w, "h": native_h},
        "screenshot_scale": used_scale if from_space == "screenshot" else infer_screenshot_scale(scale),
    }

# ─── Screenshot conversion ────────────────────────────────────────────────────

def convert_screenshot(png_path, out_path, fmt="png", scale=None, quality=80):
    from PIL import Image
    img = Image.open(png_path)

    if scale and 0 < scale < 1.0:
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)

    if fmt in ("jpeg", "jpg"):
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        if out_path.endswith(".png"):
            out_path = out_path.rsplit(".", 1)[0] + ".jpg"
        img.save(out_path, "JPEG", quality=quality)
    else:
        img.save(out_path, "PNG")

    img.close()

    if os.path.abspath(png_path) != os.path.abspath(out_path):
        try:
            os.unlink(png_path)
        except OSError:
            pass

    return out_path

# ─── Shared temp dir ──────────────────────────────────────────────────────────

def tmpdir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR

def tmpfile(prefix, ext="png"):
    return str(tmpdir() / f"{prefix}-{int(time.time()*1000)}.{ext}")

# ─── Commands ─────────────────────────────────────────────────────────────────

def cmd_screenshot(args, config):
    profile, fmt, scale, quality = capture_settings(args)

    out_path = args.out
    if not out_path:
        ext = "jpg" if fmt in ("jpeg", "jpg") else "png"
        out_path = tmpfile("screenshot", ext)
    else:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    raw_png = tmpfile(".raw", "png") if (fmt in ("jpeg", "jpg") or scale) else out_path
    actions = ["capture", raw_png]
    if getattr(args, "no_cursor", False):
        actions = ["--nocursor"] + actions

    ok, _, stderr, duration = run_vncdo(config, actions)
    if ok and os.path.exists(raw_png):
        if fmt in ("jpeg", "jpg") or scale:
            out_path = convert_screenshot(raw_png, out_path, fmt=fmt, scale=scale, quality=quality)

        img_info = get_image_info(out_path)
        image_hash = sha1_file(out_path)

        # Include coordinate mapping info for AI consumption
        native_w = img_info.get("width", 0)
        native_h = img_info.get("height", 0)
        if scale and scale < 1.0:
            native_w = int(native_w / scale)
            native_h = int(native_h / scale)

        previous = load_last_capture_state()
        unchanged = bool(previous and previous.get("sha1") == image_hash and previous.get("scale") == scale)

        state = {
            "path": str(out_path),
            "sha1": image_hash,
            "captured_at": int(time.time()),
            "scale": scale,
            "format": fmt,
            "quality": quality,
            "screenshot_w": img_info.get("width"),
            "screenshot_h": img_info.get("height"),
            "native_w": native_w,
            "native_h": native_h,
        }
        save_last_capture_state(state)

        result_json(True, {
            "action": "screenshot",
            "profile": profile,
            "image": img_info,
            "sha1": image_hash,
            "unchanged_from_previous": unchanged,
            "coordinate_space": {
                "input_space_default": "screenshot",
                "screenshot_scale": scale,
                "screenshot_w": img_info.get("width"),
                "screenshot_h": img_info.get("height"),
                "native_w": native_w,
                "native_h": native_h,
                "normalized_note": "normalized coords are 0..1 floats relative to native resolution",
                "note": "Pass screenshot-space coords to click/move/type commands. Auto-converted to native."
            },
            "duration_s": duration,
        })
    else:
        result_json(False, error=f"Screenshot failed: {stderr.strip()}")


def cmd_click(args, config):
    space = "native" if getattr(args, "native", False) else getattr(args, "space", "screenshot")
    nx, ny, native_w, native_h, used_scale = resolve_native_coords(args.x, args.y, space, config, scale=getattr(args, "scale", None))

    button_map = {"left": "1", "right": "3", "middle": "2"}
    button = button_map.get(args.button, "1")

    actions = ["move", str(nx), str(ny), "pause", "0.1", "click", button]
    if args.double:
        actions += ["pause", "0.1", "click", button]

    # Verify screenshot after click
    verify_png = tmpfile("after-click", "png")
    actions += ["pause", "0.3", "capture", verify_png]

    ok, _, stderr, duration = run_vncdo(config, actions)

    profile = get_profile(args)
    data = {
        "action": "click",
        "profile": profile,
        "input_coords": {"space": space, "x": args.x, "y": args.y},
        "native_coords": {"x": nx, "y": ny},
        "native_resolution": {"w": native_w, "h": native_h},
        "screenshot_scale_used": used_scale,
        "button": args.button,
        "double": args.double,
        "duration_s": duration,
    }

    if os.path.exists(verify_png):
        # Convert verify screenshot using active profile defaults
        _, fmt, default_scale, quality = capture_settings(args, prefer_last_scale=True)
        s = used_scale if used_scale else default_scale
        out = tmpfile("verify-click", "jpg" if fmt in ("jpeg", "jpg") else "png")
        out = convert_screenshot(verify_png, out, fmt=fmt, scale=s, quality=quality)
        data["verify_image"] = get_image_info(out)
        data["profile"] = profile

    if ok:
        result_json(True, data)
    else:
        # Still return data even on failure (verify image might exist from partial run)
        result_json(False, error=f"Click failed: {stderr.strip()}", data=data)


def cmd_move(args, config):
    space = "native" if getattr(args, "native", False) else getattr(args, "space", "screenshot")
    nx, ny, native_w, native_h, used_scale = resolve_native_coords(args.x, args.y, space, config, scale=getattr(args, "scale", None))

    # Flush with throwaway capture for reliable completion
    flush = tmpfile(".move-flush", "png")
    actions = ["move", str(nx), str(ny), "capture", flush]

    ok, _, stderr, duration = run_vncdo(config, actions)
    try:
        if os.path.exists(flush):
            os.unlink(flush)
    except OSError:
        pass

    if ok:
        result_json(True, {
            "action": "move",
            "profile": get_profile(args),
            "input_coords": {"space": space, "x": args.x, "y": args.y},
            "native_coords": {"x": nx, "y": ny},
            "native_resolution": {"w": native_w, "h": native_h},
            "screenshot_scale_used": used_scale,
            "duration_s": duration,
        })
    else:
        result_json(False, error=f"Move failed: {stderr.strip()}")


def cmd_type(args, config):
    # Type with a flush capture to ensure completion
    flush = tmpfile(".type-flush", "png")
    actions = ["type", args.text, "capture", flush]

    ok, _, stderr, duration = run_vncdo(config, actions)
    try:
        if os.path.exists(flush):
            os.unlink(flush)
    except OSError:
        pass

    if ok:
        result_json(True, {
            "action": "type",
            "text": args.text,
            "text_length": len(args.text),
            "duration_s": duration,
        })
    else:
        result_json(False, error=f"Type failed: {stderr.strip()}")


def cmd_key(args, config):
    """Send one or more key presses.

    macOS ARD often doesn't send framebuffer updates after key presses,
    causing vncdotool to hang waiting for a response. Strategy:
    - Send key(s) with short timeout
    - Treat timeout as success (key WAS sent)
    - Take a separate verify screenshot after
    """
    keys = args.keys  # list of keys
    normalized_keys = [normalize_key_name(k) for k in keys]

    # Build actions: key1 key2 ... + flush capture
    flush = tmpfile(".key-flush", "png")
    actions = []
    for k in normalized_keys:
        actions += ["key", k]
    actions += ["capture", flush]

    # Short timeout - key sends near-instantly, hang is on framebuffer
    ok, _, stderr, duration = run_vncdo(config, actions, timeout=10, timeout_ok=True)

    try:
        if os.path.exists(flush):
            os.unlink(flush)
    except OSError:
        pass

    timed_out = "timeout" in stderr.lower() if stderr else False

    if ok:
        result_json(True, {
            "action": "key",
            "keys": keys,
            "keys_sent": normalized_keys,
            "duration_s": duration,
            "timed_out": timed_out,
            "note": "Key sent successfully (framebuffer timeout is normal on macOS ARD)" if timed_out else None,
        })
    else:
        result_json(False, error=f"Key failed: {stderr.strip()}")


def cmd_combo(args, config):
    """Chain multiple VNC actions in one connection.

    Format: move,X,Y click,1 pause,0.5 type,hello key,Return

    Coordinates are in screenshot space by default (auto-converted).
    Appends a verify screenshot automatically.
    """
    profile, fmt, scale, quality = capture_settings(args, prefer_last_scale=True)
    native_mode = getattr(args, "native", False)
    input_space = "native" if native_mode else getattr(args, "space", "screenshot")

    raw_steps = args.actions
    vncdo_actions = []

    for step in raw_steps:
        parts = step.split(",")
        action = parts[0].lower()

        if action == "move" and len(parts) >= 3:
            x, y = float(parts[1]), float(parts[2])
            nx, ny, _, _, _ = resolve_native_coords(x, y, input_space, config, scale=scale)
            vncdo_actions += ["move", str(int(nx)), str(int(ny))]
        elif action == "click":
            # Supports either:
            #   click,1                -> click button 1 at current cursor
            #   click,X,Y              -> move to X,Y then left click
            #   click,X,Y,BUTTON       -> move to X,Y then click BUTTON
            if len(parts) >= 3:
                x, y = float(parts[1]), float(parts[2])
                btn = parts[3] if len(parts) >= 4 else "1"
                nx, ny, _, _, _ = resolve_native_coords(x, y, input_space, config, scale=scale)
                vncdo_actions += ["move", str(int(nx)), str(int(ny)), "click", btn]
            else:
                button = parts[1] if len(parts) > 1 else "1"
                vncdo_actions += ["click", button]
        elif action == "type" and len(parts) >= 2:
            text = ",".join(parts[1:])
            vncdo_actions += ["type", text]
        elif action == "key" and len(parts) >= 2:
            vncdo_actions += ["key", normalize_key_name(parts[1])]
        elif action == "pause" and len(parts) >= 2:
            vncdo_actions += ["pause", parts[1]]
        elif action == "capture" and len(parts) >= 2:
            vncdo_actions += ["capture", parts[1]]
        else:
            result_json(False, error=f"Unknown combo action: {step}")

    # Append verify screenshot
    raw_verify = tmpfile("combo-verify", "png")
    vncdo_actions += ["capture", raw_verify]

    ok, _, stderr, duration = run_vncdo(config, vncdo_actions, timeout=20, timeout_ok=True)

    verify_info = None
    if os.path.exists(raw_verify):
        ext = "jpg" if fmt in ("jpeg", "jpg") else "png"
        final = tmpfile("combo-final", ext)
        final = convert_screenshot(raw_verify, final, fmt=fmt, scale=scale, quality=quality)
        verify_info = get_image_info(final)

    timed_out = "timeout" in stderr.lower() if stderr else False

    if ok:
        result_json(True, {
            "action": "combo",
            "profile": profile,
            "steps": len(raw_steps),
            "input_space": input_space,
            "screenshot_scale_used": scale,
            "duration_s": duration,
            "verify_image": verify_info,
            "timed_out": timed_out,
        })
    else:
        result_json(False, error=f"Combo failed: {stderr.strip()}", data={"verify_image": verify_info})


def cmd_map(args, config):
    conv = convert_between_spaces(
        x=args.x,
        y=args.y,
        from_space=args.from_space,
        to_space=args.to_space,
        config=config,
        scale=getattr(args, "scale", None),
    )
    result_json(True, {"action": "map", **conv})


def cmd_connect(args, config):
    """Test connection, report screen dimensions and coordinate mapping."""
    tmp = tmpfile(".connect-test", "png")
    ok, _, stderr, duration = run_vncdo(config, ["capture", tmp], timeout=15)

    if ok and os.path.exists(tmp):
        try:
            from PIL import Image
            img = Image.open(tmp)
            w, h = img.width, img.height
            img.close()
        except Exception:
            w, h = None, None
        try:
            os.unlink(tmp)
        except OSError:
            pass

        profile = get_profile(args)
        scale = AI_PROFILE_DEFAULTS["scale"] if profile == "ai" else DEFAULT_SCALE
        result_json(True, {
            "action": "connect",
            "profile": profile,
            "host": config["host"],
            "port": config["port"],
            "native_resolution": {"w": w, "h": h},
            "screenshot_resolution": {
                "w": int(w * scale) if w else None,
                "h": int(h * scale) if h else None,
                "scale": scale,
            },
            "coordinate_note": f"Screenshots at {scale}x scale. Pass screenshot coords to click/move - auto-converted to native.",
            "duration_s": duration,
        })
    else:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
        result_json(False, error=f"Connection failed: {stderr.strip()}")


def cmd_status(args, config):
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


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="vnc-control",
        description="Visual bridge for AI agents. Coords in screenshot space by default.",
    )
    parser.add_argument("--host", help="VNC host (default: $VNC_HOST or 127.0.0.1)")
    parser.add_argument("--port", help="VNC port (default: $VNC_PORT or 5900)")
    parser.add_argument("--password", help="VNC password (default: $VNC_PASSWORD)")
    parser.add_argument("--username", help="VNC/ARD username (default: $VNC_USERNAME)")
    parser.add_argument("--profile", choices=["manual", "ai"], default=os.environ.get("VNC_PROFILE", DEFAULT_PROFILE),
                        help="Behavior profile: manual (flexible) or ai (efficiency-locked)")

    sub = parser.add_subparsers(dest="command", required=True)

    # screenshot
    p = sub.add_parser("screenshot", help="Capture screenshot")
    p.add_argument("--out", help="Output path (default: auto)")
    p.add_argument("--no-cursor", action="store_true")
    p.add_argument("--format", choices=["png", "jpeg", "jpg"], default=None,
                   help="Image format (auto by profile when omitted)")
    p.add_argument("--scale", type=float, default=None,
                   help="Scale 0-1 (auto by profile when omitted)")
    p.add_argument("--quality", type=int, default=None,
                   help="JPEG quality (auto by profile when omitted)")

    # click - coords in screenshot space by default
    p = sub.add_parser("click", help="Click at coordinates")
    p.add_argument("x", type=float)
    p.add_argument("y", type=float)
    p.add_argument("--button", default="left", choices=["left", "right", "middle"])
    p.add_argument("--double", action="store_true")
    p.add_argument("--space", choices=["screenshot", "native", "normalized"], default="screenshot",
                   help="Input coordinate space (default: screenshot)")
    p.add_argument("--native", action="store_true", help="Alias for --space native")
    p.add_argument("--scale", type=float, default=None,
                   help="Screenshot scale used by last/target image (auto-detected from last screenshot if omitted)")

    # move
    p = sub.add_parser("move", help="Move pointer")
    p.add_argument("x", type=float)
    p.add_argument("y", type=float)
    p.add_argument("--space", choices=["screenshot", "native", "normalized"], default="screenshot",
                   help="Input coordinate space (default: screenshot)")
    p.add_argument("--native", action="store_true", help="Alias for --space native")
    p.add_argument("--scale", type=float, default=None,
                   help="Screenshot scale used by last/target image (auto-detected from last screenshot if omitted)")

    # type
    p = sub.add_parser("type", help="Type text string")
    p.add_argument("text")

    # key - accepts multiple keys
    p = sub.add_parser("key", help="Send key press(es): e.g. key Return, key super-a")
    p.add_argument("keys", nargs="+", help="Key name(s) to press")

    # combo
    p = sub.add_parser("combo", help="Chain actions: move,X,Y click,1 type,hello key,Return")
    p.add_argument("actions", nargs="+")
    p.add_argument("--space", choices=["screenshot", "native", "normalized"], default="screenshot",
                   help="Coordinate space for move steps (default: screenshot)")
    p.add_argument("--native", action="store_true", help="Alias for --space native")
    p.add_argument("--format", choices=["png", "jpeg", "jpg"], default=None,
                   help="Verify image format (auto by profile when omitted)")
    p.add_argument("--scale", type=float, default=None,
                   help="Screenshot scale used by coordinates (auto-detected/profile default when omitted)")
    p.add_argument("--quality", type=int, default=None,
                   help="Verify image quality (auto by profile when omitted)")

    # map
    p = sub.add_parser("map", help="Convert coordinates between spaces")
    p.add_argument("x", type=float)
    p.add_argument("y", type=float)
    p.add_argument("--from", dest="from_space", choices=["screenshot", "native", "normalized"], default="screenshot")
    p.add_argument("--to", dest="to_space", choices=["screenshot", "native", "normalized"], default="native")
    p.add_argument("--scale", type=float, default=None,
                   help="Screenshot scale used by screenshot-space coords (auto-detected if omitted)")

    # connect
    sub.add_parser("connect", help="Test connection + report coordinate mapping")

    # status
    sub.add_parser("status", help="TCP reachability check")

    args = parser.parse_args()
    config = get_config(args)

    {
        "screenshot": cmd_screenshot,
        "click": cmd_click,
        "move": cmd_move,
        "type": cmd_type,
        "key": cmd_key,
        "combo": cmd_combo,
        "map": cmd_map,
        "connect": cmd_connect,
        "status": cmd_status,
    }[args.command](args, config)


if __name__ == "__main__":
    main()
