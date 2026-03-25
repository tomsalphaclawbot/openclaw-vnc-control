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
import base64
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
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

# ─── Session registry (multi-target) ─────────────────────────────────────────

SESSIONS_FILE = Path(__file__).parent / "sessions.json"


def load_sessions_config():
    """Load sessions.json if present. Returns dict with 'sessions' and 'default' keys."""
    if not SESSIONS_FILE.exists():
        return {"default": None, "sessions": {}}
    try:
        data = json.loads(SESSIONS_FILE.read_text())
        return {
            "default": data.get("default"),
            "sessions": data.get("sessions", {}),
        }
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"sessions.json parse error: {e}"}), file=sys.stderr)
        return {"default": None, "sessions": {}}


def resolve_session(session_name):
    """Resolve a named session to its config dict. Returns None if not found."""
    cfg = load_sessions_config()
    name = session_name or cfg.get("default")
    if name and name in cfg["sessions"]:
        return cfg["sessions"][name]
    return None


def list_sessions():
    """Return list of known session names."""
    cfg = load_sessions_config()
    return list(cfg["sessions"].keys()), cfg.get("default")


# ─── Connection ───────────────────────────────────────────────────────────────

def get_config(args):
    # If --session specified, load from sessions.json first
    session_name = getattr(args, "session", None)
    session_cfg = resolve_session(session_name) if session_name else None

    if session_cfg:
        # Named session wins — args can still override individual fields
        return {
            "host": getattr(args, "host", None) or session_cfg.get("host", "127.0.0.1"),
            "port": getattr(args, "port", None) or session_cfg.get("port", "5900"),
            "password": getattr(args, "password", None) or session_cfg.get("password", ""),
            "username": getattr(args, "username", None) or session_cfg.get("username", ""),
        }

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


# ─── System dialog helpers (macOS) ────────────────────────────────────────────

def detect_system_dialog():
    """Check if a macOS system dialog (TCC/permission prompt) is visible.

    Uses AppleScript to inspect UserNotificationCenter for open windows.
    Returns dict with dialog info or None if no dialog present.
    """
    script = '''
    tell application "System Events"
        set dialogInfo to {}
        try
            set notifProc to process "UserNotificationCenter"
            if (count of windows of notifProc) > 0 then
                set w to window 1 of notifProc
                set dialogTitle to ""
                try
                    set dialogTitle to name of w
                end try
                set btnStr to ""
                try
                    set allButtons to buttons of w
                    repeat with b in allButtons
                        set bLabel to ""
                        try
                            set bLabel to title of b
                        end try
                        if bLabel is "" or bLabel is missing value then
                            try
                                set bLabel to name of b
                            end try
                        end if
                        if bLabel is not missing value and bLabel is not "" then
                            if btnStr is not "" then set btnStr to btnStr & "|||"
                            set btnStr to btnStr & bLabel
                        end if
                    end repeat
                end try
                set txtStr to ""
                try
                    set allTexts to static texts of w
                    repeat with t in allTexts
                        set tVal to ""
                        try
                            set tVal to value of t
                        end try
                        if tVal is not missing value and tVal is not "" then
                            if txtStr is not "" then set txtStr to txtStr & "|||"
                            set txtStr to txtStr & tVal
                        end if
                    end repeat
                end try
                return "DIALOG_FOUND|" & dialogTitle & "|BUTTONS:" & btnStr & "|TEXT:" & txtStr
            end if
        end try
        return "NO_DIALOG"
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.strip()
        if output.startswith("DIALOG_FOUND"):
            parts = output.split("|", 3)
            title = parts[1] if len(parts) > 1 else ""
            buttons_raw = parts[2].replace("BUTTONS:", "") if len(parts) > 2 else ""
            text_raw = parts[3].replace("TEXT:", "") if len(parts) > 3 else ""
            # Parse button names (|||  delimited)
            buttons = [b.strip() for b in buttons_raw.split("|||") if b.strip()] if buttons_raw else []
            return {
                "visible": True,
                "title": title,
                "buttons": buttons,
                "text": text_raw,
                "process": "UserNotificationCenter",
            }
        return None
    except Exception:
        return None


def dismiss_system_dialog(button_name="Allow"):
    """Dismiss a macOS system dialog by clicking a named button via AppleScript.

    Returns (success: bool, message: str).
    """
    # Normalize straight quotes to curly quotes for macOS dialog matching
    # macOS uses ' (U+2019) in "Don't Allow" etc.
    button_name_curly = button_name.replace("'", "\u2019").replace("'", "\u2019")
    button_name_straight = button_name.replace("\u2019", "'").replace("\u2018", "'")

    # Use title-based matching since macOS TCC dialogs use title, not name
    script = f'''
    tell application "System Events"
        try
            set w to window 1 of process "UserNotificationCenter"
            set allButtons to buttons of w
            repeat with b in allButtons
                try
                    set bTitle to title of b
                    if bTitle is "{button_name}" or bTitle is "{button_name_curly}" or bTitle is "{button_name_straight}" then
                        click b
                        return "CLICKED"
                    end if
                end try
            end repeat
            -- Fallback: try by name
            try
                click button "{button_name}" of w
                return "CLICKED"
            end try
            return "ERROR:Button \\"{button_name}\\" not found"
        on error errMsg
            return "ERROR:" & errMsg
        end try
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.strip()
        if output == "CLICKED":
            return True, f"Clicked '{button_name}' via AppleScript accessibility API"
        else:
            return False, output.replace("ERROR:", "").strip()
    except subprocess.TimeoutExpired:
        return False, "AppleScript timed out"
    except Exception as e:
        return False, str(e)


def list_dialog_buttons():
    """List all button names on the current system dialog.

    Returns list of button name strings, or empty list if no dialog.
    """
    script = '''
    tell application "System Events"
        try
            set notifProc to process "UserNotificationCenter"
            if (count of windows of notifProc) > 0 then
                set w to window 1 of notifProc
                set btnStr to ""
                set allButtons to buttons of w
                repeat with b in allButtons
                    set bLabel to ""
                    try
                        set bLabel to title of b
                    end try
                    if bLabel is "" or bLabel is missing value then
                        try
                            set bLabel to name of b
                        end try
                    end if
                    if bLabel is not missing value and bLabel is not "" then
                        if btnStr is not "" then set btnStr to btnStr & "|||"
                        set btnStr to btnStr & bLabel
                    end if
                end repeat
                return btnStr
            end if
        end try
        return ""
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.strip()
        if output:
            return [b.strip() for b in output.split("|||") if b.strip()]
        return []
    except Exception:
        return []


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

    # Check for system dialog BEFORE clicking
    dialog_before = detect_system_dialog()

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

    # If a system dialog was visible before AND is still visible after VNC click,
    # auto-fallback to AppleScript to dismiss it
    dialog_fallback = None
    if dialog_before and dialog_before.get("visible"):
        time.sleep(0.3)
        dialog_after = detect_system_dialog()
        if dialog_after and dialog_after.get("visible"):
            # VNC click didn't dismiss the dialog — fall back to AppleScript
            # Try to figure out which button the user was targeting
            target_button = getattr(args, "dialog_button", None)
            if not target_button:
                # Heuristic: prefer affirmative buttons in priority order
                # Note: button parsing may miss some buttons, so also try
                # directly via AppleScript with common affirmative names
                available_buttons = dialog_after.get("buttons", [])
                affirmative_priority = ["Allow", "OK", "Open", "Continue", "Yes", "Install", "Allow Always"]
                for pref in affirmative_priority:
                    if pref in available_buttons:
                        target_button = pref
                        break
                if not target_button:
                    # Try affirmative buttons directly even if not in parsed list
                    # (parsing may miss them due to macOS accessibility quirks)
                    for pref in affirmative_priority:
                        test_ok, _ = dismiss_system_dialog(pref)
                        if test_ok:
                            dialog_fallback = {
                                "triggered": True,
                                "reason": "VNC click did not dismiss system dialog; auto-tried affirmative button",
                                "button_clicked": pref,
                                "method": "AppleScript accessibility API (affirmative scan)",
                                "success": True,
                                "message": f"Clicked '{pref}' via AppleScript",
                                "dialog_info": dialog_before,
                            }
                            break
                if not target_button and not dialog_fallback:
                    if available_buttons:
                        target_button = available_buttons[-1]  # rightmost = affirmative

            if dialog_fallback:
                pass  # already handled by affirmative scan above
            elif target_button:
                fallback_ok, fallback_msg = dismiss_system_dialog(target_button)
                dialog_fallback = {
                    "triggered": True,
                    "reason": "VNC click did not dismiss system dialog (macOS blocks VNC mouse events on TCC/permission dialogs)",
                    "button_clicked": target_button,
                    "method": "AppleScript accessibility API",
                    "success": fallback_ok,
                    "message": fallback_msg,
                    "dialog_info": dialog_before,
                }
            else:
                dialog_fallback = {
                    "triggered": False,
                    "reason": "System dialog detected but no button target found",
                    "dialog_info": dialog_after,
                }

    if dialog_fallback:
        data["system_dialog_fallback"] = dialog_fallback

    if os.path.exists(verify_png):
        # Convert verify screenshot using active profile defaults
        _, fmt, default_scale, quality = capture_settings(args, prefer_last_scale=True)
        s = used_scale if used_scale else default_scale
        out = tmpfile("verify-click", "jpg" if fmt in ("jpeg", "jpg") else "png")
        out = convert_screenshot(verify_png, out, fmt=fmt, scale=s, quality=quality)
        data["verify_image"] = get_image_info(out)
        data["profile"] = profile

    if ok or (dialog_fallback and dialog_fallback.get("success")):
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


def cmd_dialog(args, config):
    """Detect, inspect, and dismiss macOS system dialogs.

    Subactions:
        detect  - Check if a system dialog is visible
        dismiss - Click a button to dismiss (default: Allow)
        list    - List available buttons on the dialog
    """
    subaction = args.subaction

    if subaction == "detect":
        dialog = detect_system_dialog()
        if dialog:
            result_json(True, {
                "action": "dialog",
                "subaction": "detect",
                "dialog": dialog,
            })
        else:
            result_json(True, {
                "action": "dialog",
                "subaction": "detect",
                "dialog": None,
                "message": "No system dialog visible",
            })

    elif subaction == "dismiss":
        button_name = args.button_name or "Allow"
        dialog = detect_system_dialog()
        if not dialog:
            result_json(True, {
                "action": "dialog",
                "subaction": "dismiss",
                "message": "No system dialog to dismiss",
            })
            return

        ok, msg = dismiss_system_dialog(button_name)
        # Verify it's actually gone
        time.sleep(0.3)
        still_there = detect_system_dialog()

        result_json(ok, {
            "action": "dialog",
            "subaction": "dismiss",
            "button_clicked": button_name,
            "method": "AppleScript accessibility API",
            "success": ok,
            "message": msg,
            "dialog_before": dialog,
            "dialog_still_visible": still_there is not None,
        })

    elif subaction == "list":
        dialog = detect_system_dialog()
        if not dialog:
            result_json(True, {
                "action": "dialog",
                "subaction": "list",
                "buttons": [],
                "message": "No system dialog visible",
            })
            return

        buttons = list_dialog_buttons()
        result_json(True, {
            "action": "dialog",
            "subaction": "list",
            "buttons": buttons,
            "dialog": dialog,
        })

    else:
        result_json(False, error=f"Unknown dialog subaction: {subaction}")


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


# ─── Phase 7: Vision-Assisted Automation ─────────────────────────────────────

def _vision_find_element(image_path, description, model=None):
    """
    Call Anthropic vision API to locate a UI element described in natural language.
    Returns dict with: found (bool), x (float), y (float), confidence (str),
    reasoning (str), bounding_box (dict with x1,y1,x2,y2 or None).

    Coordinates are in SCREENSHOT space (pixels in the captured image).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {"found": False, "error": "ANTHROPIC_API_KEY not set in env"}

    # Read + encode image
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    img_b64 = base64.b64encode(img_bytes).decode()

    # Detect media type
    ext = Path(image_path).suffix.lower()
    media_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

    used_model = model or "claude-opus-4-5"

    prompt = (
        "You are a precise UI element locator. Your task is to find a specific UI element "
        "in this screenshot and return its center coordinates.\n\n"
        f"ELEMENT TO FIND: {description}\n\n"
        "Respond ONLY with a JSON object (no markdown, no explanation outside JSON) with these fields:\n"
        "- found: boolean — true if element is visible, false if not\n"
        "- x: float — center x pixel coordinate in the screenshot (null if not found)\n"
        "- y: float — center y pixel coordinate in the screenshot (null if not found)\n"
        "- confidence: string — 'high', 'medium', or 'low'\n"
        "- reasoning: string — one sentence explaining what you found and where\n"
        "- bounding_box: object with x1,y1,x2,y2 pixel coords, or null if not found\n\n"
        "Be precise. Use actual pixel coordinates from the image."
    )

    payload = {
        "model": used_model,
        "max_tokens": 512,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": img_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
    except Exception as e:
        return {"found": False, "error": f"Vision API call failed: {e}"}

    # Extract text content from response
    try:
        text = result["content"][0]["text"].strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
            if text.endswith("```"):
                text = text[: text.rfind("```")].strip()
        parsed = json.loads(text)
        return parsed
    except Exception as e:
        raw_text = result.get("content", [{}])[0].get("text", "")
        return {"found": False, "error": f"Vision response parse failed: {e}", "raw": raw_text}


def cmd_find_element(args, config):
    """
    Phase 7: find_element — locate a UI element using vision model.
    Captures a screenshot, asks the vision model to locate the described element,
    and returns its coordinates in screenshot space.
    """
    profile, fmt, scale, quality = capture_settings(args)

    # Capture screenshot
    tmp_img = tmpfile("find-element", "jpg" if fmt in ("jpeg", "jpg") else "png")
    raw_png = tmpfile(".raw-fe", "png")

    ok, _, stderr, duration = run_vncdo(config, ["capture", raw_png])
    if not ok or not os.path.exists(raw_png):
        result_json(False, error=f"Screenshot for find_element failed: {stderr.strip()}")
        return

    if fmt in ("jpeg", "jpg") or scale:
        tmp_img = convert_screenshot(raw_png, tmp_img, fmt=fmt, scale=scale, quality=quality)
    else:
        tmp_img = raw_png

    img_info = get_image_info(tmp_img)

    # Call vision model
    vision_model = getattr(args, "model", None) or os.environ.get("VNC_VISION_MODEL", "claude-opus-4-5")
    vision_result = _vision_find_element(tmp_img, args.description, model=vision_model)

    if not vision_result.get("found"):
        result_json(False, {
            "action": "find_element",
            "description": args.description,
            "found": False,
            "model": vision_model,
            "reasoning": vision_result.get("reasoning", "Element not found"),
            "error": vision_result.get("error"),
            "screenshot": {"path": tmp_img, "w": img_info.get("width"), "h": img_info.get("height")},
        })
        return

    x = vision_result.get("x")
    y = vision_result.get("y")
    confidence = vision_result.get("confidence", "unknown")
    reasoning = vision_result.get("reasoning", "")
    bbox = vision_result.get("bounding_box")

    # Compute native coords for convenience
    native_x, native_y = None, None
    if x is not None and y is not None and scale and scale > 0:
        native_x = int(x / scale)
        native_y = int(y / scale)

    result_json(True, {
        "action": "find_element",
        "description": args.description,
        "found": True,
        "x": x,
        "y": y,
        "native_x": native_x,
        "native_y": native_y,
        "confidence": confidence,
        "reasoning": reasoning,
        "bounding_box": bbox,
        "model": vision_model,
        "coordinate_space": "screenshot",
        "screenshot_scale": scale,
        "screenshot": {"path": tmp_img, "w": img_info.get("width"), "h": img_info.get("height")},
        "tip": "Use x,y with 'click' command (default screenshot space). Or use native_x,native_y with --space native.",
    })


def cmd_wait_for(args, config):
    """
    Phase 7: wait_for — screenshot loop until element/text appears (or timeout).
    Polls every --interval seconds, up to --timeout seconds.
    Returns as soon as element is found.
    """
    profile, fmt, scale, quality = capture_settings(args)
    timeout_s = getattr(args, "timeout", 30)
    interval_s = getattr(args, "interval", 2.0)
    vision_model = getattr(args, "model", None) or os.environ.get("VNC_VISION_MODEL", "claude-opus-4-5")

    start = time.time()
    attempt = 0

    while True:
        elapsed = time.time() - start
        if elapsed > timeout_s:
            result_json(False, {
                "action": "wait_for",
                "description": args.description,
                "found": False,
                "timed_out": True,
                "elapsed_s": round(elapsed, 2),
                "attempts": attempt,
                "timeout_s": timeout_s,
            })
            return

        attempt += 1
        tmp_img = tmpfile(f"wait-for-{attempt}", "jpg" if fmt in ("jpeg", "jpg") else "png")
        raw_png = tmpfile(f".raw-wf-{attempt}", "png")

        ok, _, stderr, _ = run_vncdo(config, ["capture", raw_png])
        if ok and os.path.exists(raw_png):
            if fmt in ("jpeg", "jpg") or scale:
                tmp_img = convert_screenshot(raw_png, tmp_img, fmt=fmt, scale=scale, quality=quality)
            else:
                tmp_img = raw_png

            vision_result = _vision_find_element(tmp_img, args.description, model=vision_model)
            if vision_result.get("found"):
                x = vision_result.get("x")
                y = vision_result.get("y")
                native_x = int(x / scale) if (x is not None and scale and scale > 0) else None
                native_y = int(y / scale) if (y is not None and scale and scale > 0) else None
                result_json(True, {
                    "action": "wait_for",
                    "description": args.description,
                    "found": True,
                    "elapsed_s": round(time.time() - start, 2),
                    "attempts": attempt,
                    "x": x,
                    "y": y,
                    "native_x": native_x,
                    "native_y": native_y,
                    "confidence": vision_result.get("confidence"),
                    "reasoning": vision_result.get("reasoning"),
                    "model": vision_model,
                    "screenshot": tmp_img,
                })
                return

        # Not found yet — wait and retry
        remaining = timeout_s - (time.time() - start)
        if remaining <= 0:
            continue
        time.sleep(min(interval_s, remaining))


def cmd_assert_visible(args, config):
    """
    Phase 7: assert_visible — verify a UI element or text is currently visible.
    Single screenshot + vision check. Exits 0 if found, 1 if not found.
    """
    profile, fmt, scale, quality = capture_settings(args)
    vision_model = getattr(args, "model", None) or os.environ.get("VNC_VISION_MODEL", "claude-opus-4-5")

    tmp_img = tmpfile("assert-visible", "jpg" if fmt in ("jpeg", "jpg") else "png")
    raw_png = tmpfile(".raw-av", "png")

    ok, _, stderr, _ = run_vncdo(config, ["capture", raw_png])
    if not ok or not os.path.exists(raw_png):
        print(json.dumps({"ok": False, "action": "assert_visible", "description": args.description,
                          "visible": False, "error": f"Screenshot failed: {stderr.strip()}"}))
        sys.exit(1)

    if fmt in ("jpeg", "jpg") or scale:
        tmp_img = convert_screenshot(raw_png, tmp_img, fmt=fmt, scale=scale, quality=quality)
    else:
        tmp_img = raw_png

    vision_result = _vision_find_element(tmp_img, args.description, model=vision_model)
    found = bool(vision_result.get("found"))

    payload = {
        "ok": found,
        "action": "assert_visible",
        "description": args.description,
        "visible": found,
        "confidence": vision_result.get("confidence"),
        "reasoning": vision_result.get("reasoning"),
        "x": vision_result.get("x"),
        "y": vision_result.get("y"),
        "model": vision_model,
        "screenshot": tmp_img,
    }
    if not found:
        payload["error"] = vision_result.get("error") or "Element not visible in current screenshot"

    print(json.dumps(payload))
    sys.exit(0 if found else 1)


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


def cmd_scroll(args, config):
    """Scroll at a position using mouse wheel button events.

    VNC mouse scroll is sent as button 4 (up) or 5 (down) clicks.
    Each button press = one scroll notch.
    """
    space = "native" if getattr(args, "native", False) else getattr(args, "space", "screenshot")
    nx, ny, native_w, native_h, used_scale = resolve_native_coords(args.x, args.y, space, config, scale=getattr(args, "scale", None))

    direction = args.direction.lower()
    if direction in ("up", "right"):
        button = "4"
    elif direction in ("down", "left"):
        button = "5"
    else:
        result_json(False, error=f"Unknown scroll direction: {direction!r}. Use up/down/left/right.")
        return

    clicks = max(1, min(args.clicks, 50))  # clamp 1-50

    # Build actions: move to position, then N button clicks with short pauses
    actions = ["move", str(nx), str(ny), "pause", "0.1"]
    for _ in range(clicks):
        actions += ["click", button, "pause", "0.05"]

    # Verify screenshot after scroll
    verify_png = tmpfile("after-scroll", "png")
    actions += ["pause", "0.2", "capture", verify_png]

    ok, _, stderr, duration = run_vncdo(config, actions)

    data = {
        "action": "scroll",
        "input_coords": {"space": space, "x": args.x, "y": args.y},
        "native_coords": {"x": nx, "y": ny},
        "native_resolution": {"w": native_w, "h": native_h},
        "screenshot_scale_used": used_scale,
        "direction": direction,
        "clicks": clicks,
        "vncdo_button": button,
        "duration_s": duration,
    }

    if os.path.exists(verify_png):
        _, fmt, default_scale, quality = capture_settings(args, prefer_last_scale=True)
        s = used_scale if used_scale else default_scale
        out = tmpfile("verify-scroll", "jpg" if fmt in ("jpeg", "jpg") else "png")
        out = convert_screenshot(verify_png, out, fmt=fmt, scale=s, quality=quality)
        data["verify_image"] = get_image_info(out)

    if ok:
        result_json(True, data)
    else:
        result_json(False, error=f"Scroll failed: {stderr.strip()}", data=data)


def cmd_diff(args, _config):
    """Phase 9: image diff — compare two screenshots and report changed regions.

    Loads both images (auto-resize if needed), computes per-pixel absolute diff,
    applies a threshold, then returns:
      - changed_pixels / total_pixels (change_pct)
      - bounding box of changed region (may be None if no changes)
      - path to annotated diff overlay image (highlights changes in red)
      - per-channel mean diff for quick signal
    """
    try:
        from PIL import Image, ImageDraw
        import numpy as np
    except ImportError:
        result_json(False, error="Phase 9 requires Pillow and numpy (pip install Pillow numpy)")
        return

    before_path = args.before
    after_path = args.after
    threshold = getattr(args, "threshold", 10)
    out_path = getattr(args, "out", None) or tmpfile("diff-overlay", "png")

    # Load images
    try:
        img_a = Image.open(before_path).convert("RGB")
        img_b = Image.open(after_path).convert("RGB")
    except Exception as e:
        result_json(False, error=f"Failed to open image(s): {e}")
        return

    # Resize b to match a if dimensions differ
    if img_a.size != img_b.size:
        img_b = img_b.resize(img_a.size, Image.LANCZOS)

    w, h = img_a.size
    arr_a = np.array(img_a, dtype=np.int32)
    arr_b = np.array(img_b, dtype=np.int32)

    # Per-pixel absolute diff (max across channels)
    diff = np.abs(arr_b - arr_a)
    diff_max = diff.max(axis=2)  # shape (h, w)

    mask = diff_max >= threshold
    changed_pixels = int(mask.sum())
    total_pixels = w * h
    change_pct = round(changed_pixels / total_pixels * 100, 4) if total_pixels else 0

    # Bounding box of changed region
    bbox = None
    if changed_pixels > 0:
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        row_idxs = np.where(rows)[0]
        col_idxs = np.where(cols)[0]
        rmin, rmax = int(row_idxs[0]), int(row_idxs[-1])
        cmin, cmax = int(col_idxs[0]), int(col_idxs[-1])
        bbox = {"x": cmin, "y": rmin, "x2": cmax, "y2": rmax,
                "width": cmax - cmin + 1, "height": rmax - rmin + 1}

    # Per-channel mean diff
    mean_diff = {
        "r": round(float(diff[:, :, 0].mean()), 3),
        "g": round(float(diff[:, :, 1].mean()), 3),
        "b": round(float(diff[:, :, 2].mean()), 3),
    }

    # Annotated overlay: blend diff highlight in red over after-image
    overlay = img_b.copy()
    overlay_arr = np.array(overlay, dtype=np.uint8)
    # Red highlight at changed pixels (intensity proportional to diff_max, clamped)
    intensity = np.clip(diff_max * 3, 0, 255).astype(np.uint8)
    overlay_arr[mask, 0] = np.clip(overlay_arr[mask, 0].astype(np.int32) + intensity[mask], 0, 255).astype(np.uint8)
    overlay_arr[mask, 1] = (overlay_arr[mask, 1] * 0.4).astype(np.uint8)
    overlay_arr[mask, 2] = (overlay_arr[mask, 2] * 0.4).astype(np.uint8)
    overlay = Image.fromarray(overlay_arr)

    # Draw bounding box rectangle if changed region exists
    if bbox:
        draw = ImageDraw.Draw(overlay)
        draw.rectangle(
            [(bbox["x"], bbox["y"]), (bbox["x2"], bbox["y2"])],
            outline=(255, 80, 0), width=3
        )

    overlay.save(str(out_path))

    result_json(True, {
        "action": "diff",
        "before": str(before_path),
        "after": str(after_path),
        "image_size": {"width": w, "height": h},
        "threshold": threshold,
        "changed_pixels": changed_pixels,
        "total_pixels": total_pixels,
        "change_pct": change_pct,
        "changed": changed_pixels > 0,
        "bounding_box": bbox,
        "mean_diff_per_channel": mean_diff,
        "overlay_image": get_image_info(str(out_path)),
        "tip": "change_pct > 1% typically indicates visible UI change; bounding_box gives region to inspect.",
    })


def cmd_drag(args, config):
    """Drag from (x1,y1) to (x2,y2) by holding the mouse button down.

    Uses vncdo mousedown → drag → mouseup sequence.
    The 'drag' action in vncdo moves the mouse in small steps (smoother).
    """
    space = "native" if getattr(args, "native", False) else getattr(args, "space", "screenshot")

    nx1, ny1, native_w, native_h, used_scale = resolve_native_coords(
        args.x1, args.y1, space, config, scale=getattr(args, "scale", None)
    )
    nx2, ny2, _, _, _ = resolve_native_coords(
        args.x2, args.y2, space, config, scale=getattr(args, "scale", None)
    )

    button_map = {"left": "1", "right": "3", "middle": "2"}
    button = button_map.get(getattr(args, "button", "left"), "1")

    # Move to start, mousedown, drag to end, mouseup
    verify_png = tmpfile("after-drag", "png")
    actions = [
        "move", str(nx1), str(ny1), "pause", "0.1",
        "mousedown", button, "pause", "0.05",
        "drag", str(nx2), str(ny2), "pause", "0.1",
        "mouseup", button, "pause", "0.2",
        "capture", verify_png,
    ]

    ok, _, stderr, duration = run_vncdo(config, actions)

    data = {
        "action": "drag",
        "from": {"space": space, "x": args.x1, "y": args.y1},
        "to": {"space": space, "x": args.x2, "y": args.y2},
        "from_native": {"x": nx1, "y": ny1},
        "to_native": {"x": nx2, "y": ny2},
        "native_resolution": {"w": native_w, "h": native_h},
        "screenshot_scale_used": used_scale,
        "button": getattr(args, "button", "left"),
        "duration_s": duration,
    }

    if os.path.exists(verify_png):
        _, fmt, default_scale, quality = capture_settings(args, prefer_last_scale=True)
        s = used_scale if used_scale else default_scale
        out = tmpfile("verify-drag", "jpg" if fmt in ("jpeg", "jpg") else "png")
        out = convert_screenshot(verify_png, out, fmt=fmt, scale=s, quality=quality)
        data["verify_image"] = get_image_info(out)

    if ok:
        result_json(True, data)
    else:
        result_json(False, error=f"Drag failed: {stderr.strip()}", data=data)


def cmd_crop(args, _config):
    """Phase 10: Region-of-Interest (ROI) crop.

    Crops an existing screenshot to a bounding box (x, y, x2, y2) in screenshot
    space, and saves the cropped region as a new image.

    Coordinate input:
      --space screenshot (default): coords in screenshot-space pixels
      --space native: coords in native VNC pixels (divided by scale)
      --space normalized: coords as 0..1 fractions of screenshot dimensions

    Use cases:
      - Feed a focused crop to vision API instead of full screen (cheaper/faster)
      - Isolate a form, dialog, or region for targeted analysis
      - Compare crops before/after an action for precise change detection

    Returns JSON with the cropped image path, dimensions, and source bounding box.
    """
    try:
        from PIL import Image
    except ImportError:
        result_json(False, error="Phase 10 requires Pillow (pip install Pillow)")
        return

    src_path = args.source
    if not os.path.exists(src_path):
        result_json(False, error=f"Source image not found: {src_path}")
        return

    try:
        img = Image.open(src_path)
    except Exception as e:
        result_json(False, error=f"Cannot open source image: {e}")
        return

    img_w, img_h = img.size
    space = getattr(args, "space", "screenshot")

    # Parse crop coordinates
    x1_in = args.x1
    y1_in = args.y1
    x2_in = args.x2
    y2_in = args.y2

    if space == "normalized":
        # Normalized: 0..1 fractions relative to image dimensions
        x1 = int(x1_in * img_w)
        y1 = int(y1_in * img_h)
        x2 = int(x2_in * img_w)
        y2 = int(y2_in * img_h)
    elif space == "native":
        # Native VNC coords: determine scale used when screenshot was captured
        last = load_last_capture_state()
        scale = last.get("scale", DEFAULT_SCALE) if last else DEFAULT_SCALE
        if scale and scale > 0:
            x1 = int(x1_in * scale)
            y1 = int(y1_in * scale)
            x2 = int(x2_in * scale)
            y2 = int(y2_in * scale)
        else:
            x1, y1, x2, y2 = int(x1_in), int(y1_in), int(x2_in), int(y2_in)
    else:
        # Screenshot space: direct pixel coords in the source image
        x1, y1, x2, y2 = int(x1_in), int(y1_in), int(x2_in), int(y2_in)

    # Ensure x1 < x2 and y1 < y2
    if x1 > x2:
        x1, x2 = x2, x1
    if y1 > y2:
        y1, y2 = y2, y1

    # Clamp to image bounds
    x1 = max(0, min(x1, img_w))
    y1 = max(0, min(y1, img_h))
    x2 = max(0, min(x2, img_w))
    y2 = max(0, min(y2, img_h))

    if x2 <= x1 or y2 <= y1:
        result_json(False, error=f"Invalid crop region: ({x1},{y1})→({x2},{y2}) — zero or negative area after clamping")
        img.close()
        return

    # Crop
    cropped = img.crop((x1, y1, x2, y2))
    img.close()

    # Determine output path
    out_path = getattr(args, "out", None)
    if not out_path:
        fmt_ext = "jpg" if getattr(args, "format", None) in (None, "jpeg", "jpg") else "png"
        out_path = tmpfile("crop", fmt_ext)
    else:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    out_fmt = getattr(args, "format", None) or "jpeg"
    quality = getattr(args, "quality", None) or DEFAULT_QUALITY

    if out_fmt in ("jpeg", "jpg"):
        if cropped.mode in ("RGBA", "LA", "P"):
            cropped = cropped.convert("RGB")
        if not out_path.endswith(".jpg") and not out_path.endswith(".jpeg"):
            out_path = out_path.rsplit(".", 1)[0] + ".jpg" if "." in out_path else out_path + ".jpg"
        cropped.save(out_path, "JPEG", quality=quality)
    else:
        cropped.save(out_path, "PNG")

    cropped.close()

    crop_w = x2 - x1
    crop_h = y2 - y1
    out_info = get_image_info(out_path)

    result_json(True, {
        "action": "crop",
        "source": src_path,
        "source_dimensions": {"w": img_w, "h": img_h},
        "input_space": space,
        "input_coords": {"x1": x1_in, "y1": y1_in, "x2": x2_in, "y2": y2_in},
        "screenshot_coords": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "crop_dimensions": {"w": crop_w, "h": crop_h},
        "coverage_pct": round(100.0 * crop_w * crop_h / (img_w * img_h), 1) if img_w * img_h else 0,
        "output": out_info,
        "tip": "Feed the output path to find_element/assert_visible by taking a screenshot first, then crop to focus region.",
    })


def cmd_annotate(args, _config):
    """Phase 11: Annotate a screenshot with labeled shapes.

    Draws rectangles, circles, arrows, and/or text labels on a screenshot
    to highlight regions of interest. Useful for AI inspection, debugging,
    documentation, and visual diff workflows.

    Shape specs (--shape flags, repeatable):
      rect:X1,Y1,X2,Y2[,COLOR[,LABEL]]   — filled/outlined rectangle
      circle:CX,CY,R[,COLOR[,LABEL]]     — circle at center (CX,CY) radius R
      arrow:X1,Y1,X2,Y2[,COLOR[,LABEL]]  — arrow from (X1,Y1) → (X2,Y2)
      text:X,Y,TEXT[,COLOR]              — text annotation at (X,Y)

    All coordinates in screenshot space by default (same image pixels).
    COLOR defaults to red (#FF0000) if omitted.
    LABEL is optional descriptive text drawn beside the shape.

    Returns JSON with annotated image path and a list of drawn shapes.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        result_json(False, error="Phase 11 requires Pillow (pip install Pillow)")
        return

    src_path = args.source
    if not os.path.exists(src_path):
        result_json(False, error=f"Source image not found: {src_path}")
        return

    try:
        img = Image.open(src_path).convert("RGBA")
    except Exception as e:
        result_json(False, error=f"Cannot open source image: {e}")
        return

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Font selection — use default PIL bitmap font (always available, no external dep)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except Exception:
        font = ImageFont.load_default()
        font_large = font

    def parse_color(color_str):
        """Parse color string to RGBA tuple."""
        if not color_str:
            return (255, 50, 50, 220)  # default: semi-transparent red
        # Named colors first (before trying hex parse)
        named = {
            "red": (255, 50, 50, 220),
            "green": (50, 205, 50, 220),
            "blue": (50, 100, 255, 220),
            "yellow": (255, 220, 0, 220),
            "orange": (255, 140, 0, 220),
            "purple": (160, 50, 200, 220),
            "white": (255, 255, 255, 220),
            "black": (0, 0, 0, 220),
            "cyan": (0, 210, 210, 220),
            "pink": (255, 100, 180, 220),
        }
        if color_str.lower() in named:
            return named[color_str.lower()]
        # Try hex
        s = color_str.strip().lstrip("#")
        if len(s) == 6:
            try:
                r = int(s[0:2], 16)
                g = int(s[2:4], 16)
                b = int(s[4:6], 16)
                return (r, g, b, 220)
            except ValueError:
                pass
        return (255, 50, 50, 220)  # fallback to red

    shapes_drawn = []
    line_width = max(2, getattr(args, "line_width", 2))

    shape_specs = getattr(args, "shape", []) or []
    for spec in shape_specs:
        # parse: kind:param1,param2,...
        if ":" not in spec:
            continue
        kind, rest = spec.split(":", 1)
        parts = rest.split(",")
        kind = kind.strip().lower()

        try:
            if kind == "rect":
                # rect:X1,Y1,X2,Y2[,COLOR[,LABEL]]
                x1, y1, x2, y2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                color = parse_color(parts[4] if len(parts) > 4 else None)
                label = parts[5] if len(parts) > 5 else None
                # Draw rectangle outline
                draw.rectangle([x1, y1, x2, y2], outline=color, width=line_width)
                # Semi-transparent fill
                fill_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                fill_draw = ImageDraw.Draw(fill_overlay)
                fill_color = (color[0], color[1], color[2], 40)
                fill_draw.rectangle([x1, y1, x2, y2], fill=fill_color)
                overlay = Image.alpha_composite(overlay, fill_overlay)
                draw = ImageDraw.Draw(overlay)
                # Label
                if label:
                    draw.text((x1 + 3, y1 - 18), label, fill=color, font=font)
                shapes_drawn.append({"type": "rect", "coords": [x1, y1, x2, y2], "color": f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}", "label": label})

            elif kind == "circle":
                # circle:CX,CY,R[,COLOR[,LABEL]]
                cx, cy, r = int(parts[0]), int(parts[1]), int(parts[2])
                color = parse_color(parts[3] if len(parts) > 3 else None)
                label = parts[4] if len(parts) > 4 else None
                bbox = [cx - r, cy - r, cx + r, cy + r]
                draw.ellipse(bbox, outline=color, width=line_width)
                if label:
                    draw.text((cx + r + 4, cy - 8), label, fill=color, font=font)
                shapes_drawn.append({"type": "circle", "center": [cx, cy], "radius": r, "color": f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}", "label": label})

            elif kind == "arrow":
                # arrow:X1,Y1,X2,Y2[,COLOR[,LABEL]]
                x1, y1, x2, y2 = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                color = parse_color(parts[4] if len(parts) > 4 else None)
                label = parts[5] if len(parts) > 5 else None
                # Shaft
                draw.line([(x1, y1), (x2, y2)], fill=color, width=line_width)
                # Arrowhead: compute perpendicular offset
                import math
                dx, dy = x2 - x1, y2 - y1
                length = math.hypot(dx, dy)
                if length > 0:
                    head_len = max(10, min(20, int(length * 0.25)))
                    ux, uy = dx / length, dy / length  # unit vector
                    # Two arrowhead corners
                    perp_x, perp_y = -uy, ux
                    hw = head_len * 0.4  # half-width of arrowhead base
                    p1 = (x2 - ux * head_len + perp_x * hw, y2 - uy * head_len + perp_y * hw)
                    p2 = (x2 - ux * head_len - perp_x * hw, y2 - uy * head_len - perp_y * hw)
                    draw.polygon([(x2, y2), p1, p2], fill=color)
                if label:
                    mx, my = (x1 + x2) // 2, (y1 + y2) // 2
                    draw.text((mx + 4, my - 8), label, fill=color, font=font)
                shapes_drawn.append({"type": "arrow", "from": [x1, y1], "to": [x2, y2], "color": f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}", "label": label})

            elif kind == "text":
                # text:X,Y,TEXT[,COLOR]
                x, y = int(parts[0]), int(parts[1])
                text = parts[2].replace("_", " ") if len(parts) > 2 else "?"
                color = parse_color(parts[3] if len(parts) > 3 else None)
                # Background box for readability
                bbox = draw.textbbox((x, y), text, font=font_large)
                pad = 3
                draw.rectangle([bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad],
                               fill=(0, 0, 0, 160))
                draw.text((x, y), text, fill=color, font=font_large)
                shapes_drawn.append({"type": "text", "pos": [x, y], "text": text, "color": f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"})

        except (ValueError, IndexError) as e:
            # Skip malformed shape specs
            shapes_drawn.append({"type": kind, "error": str(e), "spec": spec})

    # Composite overlay onto image
    result_img = Image.alpha_composite(img, overlay)

    # Output path
    out_path = getattr(args, "out", None)
    if not out_path:
        out_path = tmpfile("annotate", "jpg")

    out_fmt = getattr(args, "format", None) or "jpeg"
    quality = getattr(args, "quality", None) or DEFAULT_QUALITY

    if out_fmt in ("jpeg", "jpg"):
        result_img_rgb = result_img.convert("RGB")
        if not (out_path.endswith(".jpg") or out_path.endswith(".jpeg")):
            out_path = (out_path.rsplit(".", 1)[0] + ".jpg") if "." in out_path else (out_path + ".jpg")
        result_img_rgb.save(out_path, "JPEG", quality=quality)
    else:
        result_img.save(out_path, "PNG")

    result_img.close()
    img.close()

    out_info = get_image_info(out_path)
    result_json(True, {
        "action": "annotate",
        "source": src_path,
        "shapes_drawn": len(shapes_drawn),
        "shapes": shapes_drawn,
        "output": out_info,
        "tip": "Use rect/circle shapes to highlight UI elements, arrow to indicate click targets, text to add labels.",
    })


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
    parser.add_argument("--session", "-S",
                        help="Named session from sessions.json (overrides env/arg host/port/creds)")
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

    # dialog - detect/dismiss macOS system dialogs
    p = sub.add_parser("dialog", help="Detect, inspect, and dismiss macOS system dialogs (TCC prompts)")
    p.add_argument("subaction", choices=["detect", "dismiss", "list"],
                   help="detect: check for visible dialog | dismiss: click a button | list: show available buttons")
    p.add_argument("--button", dest="button_name", default=None,
                   help="Button to click for dismiss (default: Allow)")

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

    # find_element - Phase 7 vision-assisted UI element location
    p = sub.add_parser("find_element", help="[Phase 7] Locate a UI element using vision model")
    p.add_argument("description", help="Natural language description of element to find (e.g. 'Save button', 'username input field')")
    p.add_argument("--model", default=None, help="Vision model to use (default: claude-opus-4-5 or $VNC_VISION_MODEL)")
    p.add_argument("--format", choices=["png", "jpeg", "jpg"], default=None)
    p.add_argument("--scale", type=float, default=None)
    p.add_argument("--quality", type=int, default=None)

    # wait_for - Phase 7 vision-assisted element wait loop
    p = sub.add_parser("wait_for", help="[Phase 7] Wait until an element appears (vision loop)")
    p.add_argument("description", help="Natural language description of element to wait for")
    p.add_argument("--timeout", type=float, default=30, help="Max wait time in seconds (default: 30)")
    p.add_argument("--interval", type=float, default=2.0, help="Poll interval in seconds (default: 2.0)")
    p.add_argument("--model", default=None, help="Vision model to use (default: claude-opus-4-5 or $VNC_VISION_MODEL)")
    p.add_argument("--format", choices=["png", "jpeg", "jpg"], default=None)
    p.add_argument("--scale", type=float, default=None)
    p.add_argument("--quality", type=int, default=None)

    # assert_visible - Phase 7 vision-based UI state assertion
    p = sub.add_parser("assert_visible", help="[Phase 7] Assert an element/text is visible (exit 0=found, 1=not found)")
    p.add_argument("description", help="Natural language description of element to verify")
    p.add_argument("--model", default=None, help="Vision model to use (default: claude-opus-4-5 or $VNC_VISION_MODEL)")
    p.add_argument("--format", choices=["png", "jpeg", "jpg"], default=None)
    p.add_argument("--scale", type=float, default=None)
    p.add_argument("--quality", type=int, default=None)

    # scroll - Phase 8: mouse wheel scrolling
    p = sub.add_parser("scroll", help="[Phase 8] Scroll at a position (mouse wheel)")
    p.add_argument("x", type=float, help="X coordinate (screenshot space by default)")
    p.add_argument("y", type=float, help="Y coordinate (screenshot space by default)")
    p.add_argument("direction", choices=["up", "down", "left", "right"],
                   help="Scroll direction")
    p.add_argument("--clicks", type=int, default=3,
                   help="Number of scroll notches (default: 3, max: 50)")
    p.add_argument("--space", choices=["screenshot", "native", "normalized"], default="screenshot",
                   help="Input coordinate space (default: screenshot)")
    p.add_argument("--native", action="store_true", help="Alias for --space native")
    p.add_argument("--scale", type=float, default=None,
                   help="Screenshot scale used by coordinates (auto-detected if omitted)")

    # diff - Phase 9: image diff between two screenshots
    p = sub.add_parser("diff", help="[Phase 9] Compare two screenshots and report changed regions")
    p.add_argument("before", help="Path to before-screenshot (reference image)")
    p.add_argument("after", help="Path to after-screenshot (image to compare)")
    p.add_argument("--threshold", type=int, default=10,
                   help="Pixel change threshold (0-255, default: 10). Lower = more sensitive.")
    p.add_argument("--out", default=None,
                   help="Output path for annotated diff overlay image (default: auto-temp)")

    # drag - Phase 8: click-and-drag between two points
    p = sub.add_parser("drag", help="[Phase 8] Drag from (x1,y1) to (x2,y2)")
    p.add_argument("x1", type=float, help="Start X (screenshot space by default)")
    p.add_argument("y1", type=float, help="Start Y (screenshot space by default)")
    p.add_argument("x2", type=float, help="End X (screenshot space by default)")
    p.add_argument("y2", type=float, help="End Y (screenshot space by default)")
    p.add_argument("--button", default="left", choices=["left", "right", "middle"],
                   help="Mouse button to hold during drag (default: left)")
    p.add_argument("--space", choices=["screenshot", "native", "normalized"], default="screenshot",
                   help="Input coordinate space (default: screenshot)")
    p.add_argument("--native", action="store_true", help="Alias for --space native")
    p.add_argument("--scale", type=float, default=None,
                   help="Screenshot scale used by coordinates (auto-detected if omitted)")

    # crop - Phase 10: Region-of-Interest crop
    p = sub.add_parser("crop", help="[Phase 10] Crop a screenshot to a bounding box region")
    p.add_argument("source", help="Path to source screenshot image")
    p.add_argument("x1", type=float, help="Left edge of crop region")
    p.add_argument("y1", type=float, help="Top edge of crop region")
    p.add_argument("x2", type=float, help="Right edge of crop region")
    p.add_argument("y2", type=float, help="Bottom edge of crop region")
    p.add_argument("--space", choices=["screenshot", "native", "normalized"], default="screenshot",
                   help="Coordinate space for x1/y1/x2/y2 (default: screenshot)")
    p.add_argument("--out", default=None, help="Output path for cropped image (default: auto-temp)")
    p.add_argument("--format", choices=["png", "jpeg", "jpg"], default=None,
                   help="Output format (default: jpeg)")
    p.add_argument("--quality", type=int, default=None,
                   help="JPEG quality (default: 80)")

    # annotate - Phase 11: draw labeled shapes on a screenshot
    p = sub.add_parser("annotate", help="[Phase 11] Annotate a screenshot with rectangles, circles, arrows, text")
    p.add_argument("source", help="Path to source screenshot image")
    p.add_argument("--shape", action="append", metavar="SPEC",
                   help="Shape spec (repeatable). Formats: "
                        "rect:X1,Y1,X2,Y2[,COLOR[,LABEL]] | "
                        "circle:CX,CY,R[,COLOR[,LABEL]] | "
                        "arrow:X1,Y1,X2,Y2[,COLOR[,LABEL]] | "
                        "text:X,Y,TEXT[,COLOR]. "
                        "COLOR = hex (#FF0000) or name (red/green/blue/yellow/orange/purple/cyan/pink/white/black)")
    p.add_argument("--line-width", type=int, default=2,
                   help="Line/border width in pixels (default: 2)")
    p.add_argument("--out", default=None, help="Output path for annotated image (default: auto-temp)")
    p.add_argument("--format", choices=["png", "jpeg", "jpg"], default=None,
                   help="Output format (default: jpeg)")
    p.add_argument("--quality", type=int, default=None,
                   help="JPEG quality (default: 80)")

    # sessions - list/show named session registry
    p = sub.add_parser("sessions", help="List or inspect named sessions from sessions.json")
    p.add_argument("subaction", nargs="?", choices=["list", "show"], default="list",
                   help="list: show all sessions | show NAME: show a specific session config")
    p.add_argument("name", nargs="?", default=None, help="Session name for 'show'")

    args = parser.parse_args()
    config = get_config(args)

    if args.command == "sessions":
        _cmd_sessions(args)
        return

    {
        "screenshot": cmd_screenshot,
        "click": cmd_click,
        "move": cmd_move,
        "type": cmd_type,
        "key": cmd_key,
        "combo": cmd_combo,
        "dialog": cmd_dialog,
        "map": cmd_map,
        "connect": cmd_connect,
        "status": cmd_status,
        "find_element": cmd_find_element,
        "wait_for": cmd_wait_for,
        "assert_visible": cmd_assert_visible,
        "scroll": cmd_scroll,
        "drag": cmd_drag,
        "diff": cmd_diff,
        "crop": cmd_crop,
        "annotate": cmd_annotate,
    }[args.command](args, config)


def _cmd_sessions(args):
    """Handle the 'sessions' subcommand."""
    subaction = getattr(args, "subaction", "list") or "list"
    name = getattr(args, "name", None)
    sessions, default = list_sessions()

    if subaction == "show" and name:
        cfg = resolve_session(name)
        if cfg is None:
            result_json(False, error=f"Session '{name}' not found. Known sessions: {sessions}")
        else:
            # Redact password for display
            display = {**cfg}
            if display.get("password"):
                display["password"] = "***"
            result_json(True, {"session": name, "config": display, "default": name == default})
    else:
        if not sessions:
            result_json(True, {
                "sessions": [],
                "default": None,
                "note": "No sessions.json found. Copy sessions.json.example to sessions.json to get started.",
            })
        else:
            result_json(True, {"sessions": sessions, "default": default, "count": len(sessions)})


if __name__ == "__main__":
    main()
