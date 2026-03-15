#!/usr/bin/env python3
"""
vnc-session — Persistent VNC session daemon + CLI.

Architecture: daemon keeps ONE vncdotool API connection alive.
Commands arrive via Unix socket — zero reconnection overhead.
Background keepalive prevents macOS screen lock.

Daemon:   vnc start
Commands: vnc ss / vnc click X Y / vnc type "hello" / vnc key return
Stop:     vnc stop
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

# --- Paths ---
SOCK_DIR = Path(os.environ.get("VNC_RUNTIME_DIR", "/tmp/vnc-session"))
SOCK_PATH = SOCK_DIR / "vnc.sock"
PID_FILE = SOCK_DIR / "vnc.pid"
LOG_FILE = SOCK_DIR / "daemon.log"
CAPTURE_DIR = SOCK_DIR / "captures"

# --- Defaults ---
DEFAULT_SCALE = 0.5
DEFAULT_FMT = "jpeg"
DEFAULT_QUALITY = 80
KEEPALIVE_SEC = 25
API_TIMEOUT = 25  # macOS ARD needs ~15s for first framebuffer


def load_env():
    """Load .env from project dir. Doesn't override existing env."""
    envfile = Path(__file__).parent / ".env"
    if envfile.is_file():
        for line in envfile.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def vnc_cfg():
    return {
        "host": os.environ.get("VNC_HOST", "127.0.0.1"),
        "port": os.environ.get("VNC_PORT", "5900"),
        "password": os.environ.get("VNC_PASSWORD") or None,
        "username": os.environ.get("VNC_USERNAME") or None,
    }


# ============================================================
# DAEMON — persistent vncdotool API connection
# ============================================================

class Daemon:
    def __init__(self, cfg):
        self.cfg = cfg
        self.client = None
        self.lock = threading.Lock()
        self.alive = True
        self.native_w = 3420  # updated on first screenshot
        self.native_h = 2214
        self.last_scale = DEFAULT_SCALE
        self._connect()

    def _connect(self):
        from vncdotool import api
        self.client = api.connect(
            f"{self.cfg['host']}::{self.cfg['port']}",
            password=self.cfg["password"],
            username=self.cfg["username"],
            timeout=API_TIMEOUT,
        )

    def _reconnect(self):
        try:
            self.client.disconnect()
        except Exception:
            pass
        self._connect()

    def _with_retry(self, fn):
        """Run fn; on failure, reconnect and retry once."""
        try:
            return fn()
        except Exception:
            self._reconnect()
            return fn()

    def screenshot(self, out=None, fmt=DEFAULT_FMT, scale=DEFAULT_SCALE, quality=DEFAULT_QUALITY):
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        ts = int(time.time() * 1000)
        raw = str(CAPTURE_DIR / f".raw-{ts}.png")

        t0 = time.time()
        with self.lock:
            self._with_retry(lambda: self.client.captureScreen(raw))
        dur = round(time.time() - t0, 2)

        from PIL import Image
        img = Image.open(raw)
        self.native_w, self.native_h = img.width, img.height
        self.last_scale = scale or 1.0

        if scale and 0 < scale < 1.0:
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)

        ext = "jpg" if fmt in ("jpeg", "jpg") else "png"
        final = out or str(CAPTURE_DIR / f"screen-{ts}.{ext}")

        if fmt in ("jpeg", "jpg"):
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(final, "JPEG", quality=quality)
        else:
            img.save(final, "PNG")

        cw, ch = img.width, img.height
        img.close()
        try:
            os.unlink(raw)
        except OSError:
            pass

        return {
            "ok": True, "path": final,
            "native_w": self.native_w, "native_h": self.native_h,
            "capture_w": cw, "capture_h": ch,
            "scale": self.last_scale,
            "size_kb": round(os.path.getsize(final) / 1024),
            "duration_s": dur,
        }

    def click(self, x, y, button="left", double=False, space="capture"):
        nx, ny = self._to_native(x, y, space)
        btn = {"left": 1, "right": 3, "middle": 2}.get(button, 1)
        with self.lock:
            def do():
                self.client.mouseMove(nx, ny)
                self.client.mousePress(btn)
                if double:
                    time.sleep(0.05)
                    self.client.mousePress(btn)
            self._with_retry(do)
        return {"ok": True, "native_x": nx, "native_y": ny, "button": button}

    def move(self, x, y, space="capture"):
        nx, ny = self._to_native(x, y, space)
        with self.lock:
            self._with_retry(lambda: self.client.mouseMove(nx, ny))
        return {"ok": True, "native_x": nx, "native_y": ny}

    def type_text(self, text):
        with self.lock:
            self._with_retry(lambda: self.client.paste(text))
        return {"ok": True, "length": len(text)}

    def key(self, keyname):
        with self.lock:
            self._with_retry(lambda: self.client.keyPress(keyname))
        return {"ok": True, "key": keyname}

    def _to_native(self, x, y, space):
        x, y = float(x), float(y)
        if space in ("native",):
            return int(x), int(y)
        elif space in ("normalized", "n"):
            return int(x * self.native_w), int(y * self.native_h)
        elif space in ("capture", "c"):
            factor = 1.0 / self.last_scale if self.last_scale > 0 else 2.0
            return int(x * factor), int(y * factor)
        return int(x), int(y)

    def keepalive_loop(self):
        """Periodic micro-jiggle in screen center to prevent macOS lock."""
        while self.alive:
            time.sleep(KEEPALIVE_SEC)
            if not self.alive:
                break
            try:
                cx, cy = self.native_w // 2, self.native_h // 2
                with self.lock:
                    self.client.mouseMove(cx, cy)
                    self.client.mouseMove(cx + 1, cy)
            except Exception:
                pass  # reconnect happens on next real command

    def status(self):
        alive = True
        try:
            with self.lock:
                self.client.mouseMove(self.native_w // 2, self.native_h // 2)
        except Exception:
            alive = False
        return {
            "ok": True, "alive": alive,
            "native_w": self.native_w, "native_h": self.native_h,
            "last_scale": self.last_scale, "pid": os.getpid(),
        }

    def shutdown(self):
        self.alive = False
        try:
            self.client.disconnect()
        except Exception:
            pass


def run_daemon():
    load_env()
    cfg = vnc_cfg()

    SOCK_DIR.mkdir(parents=True, exist_ok=True)
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    SOCK_PATH.unlink(missing_ok=True)

    # Redirect stderr to log
    sys.stderr = open(LOG_FILE, "w")

    try:
        d = Daemon(cfg)
        # Warm up: first captureScreen forces full framebuffer fetch (~1-2s)
        # Without this, the first client request would pay the ~15s ARD penalty
        warmup = str(CAPTURE_DIR / ".warmup.png")
        d.client.captureScreen(warmup)
        from PIL import Image
        img = Image.open(warmup)
        d.native_w, d.native_h = img.width, img.height
        img.close()
        try:
            os.unlink(warmup)
        except OSError:
            pass
    except Exception as e:
        msg = json.dumps({"ok": False, "error": f"VNC connect failed: {e}"})
        print(msg)
        sys.stderr.write(msg + "\n")
        sys.exit(1)

    PID_FILE.write_text(str(os.getpid()))

    ka = threading.Thread(target=d.keepalive_loop, daemon=True)
    ka.start()

    def stop_handler(sig, frame):
        d.shutdown()
        SOCK_PATH.unlink(missing_ok=True)
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(SOCK_PATH))
    srv.listen(2)
    srv.settimeout(1.0)

    print(json.dumps({"ok": True, "action": "started", "pid": os.getpid(), "socket": str(SOCK_PATH)}))
    sys.stdout.flush()

    while d.alive:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        except Exception:
            break

        try:
            data = b""
            conn.settimeout(30)
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            req = json.loads(data.decode())
            cmd = req.get("cmd", "")

            if cmd == "stop":
                d.alive = False
                resp = {"ok": True, "action": "stopping"}
            elif cmd == "screenshot":
                resp = d.screenshot(req.get("out"), req.get("format", DEFAULT_FMT),
                                     req.get("scale", DEFAULT_SCALE), req.get("quality", DEFAULT_QUALITY))
            elif cmd == "click":
                resp = d.click(req["x"], req["y"], req.get("button", "left"),
                                req.get("double", False), req.get("space", "capture"))
            elif cmd == "move":
                resp = d.move(req["x"], req["y"], req.get("space", "capture"))
            elif cmd == "type":
                resp = d.type_text(req["text"])
            elif cmd == "key":
                resp = d.key(req["key"])
            elif cmd == "status":
                resp = d.status()
            else:
                resp = {"ok": False, "error": f"unknown: {cmd}"}

            conn.sendall((json.dumps(resp) + "\n").encode())
        except Exception as e:
            try:
                conn.sendall((json.dumps({"ok": False, "error": str(e)}) + "\n").encode())
            except Exception:
                pass
        finally:
            conn.close()

    d.shutdown()
    SOCK_PATH.unlink(missing_ok=True)
    PID_FILE.unlink(missing_ok=True)


# ============================================================
# CLI CLIENT
# ============================================================

def send(req):
    if not SOCK_PATH.exists():
        return {"ok": False, "error": "not running. Run: vnc start"}
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(30)
    try:
        sock.connect(str(SOCK_PATH))
        sock.sendall((json.dumps(req) + "\n").encode())
        data = b""
        while True:
            chunk = sock.recv(8192)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        return json.loads(data.decode())
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        sock.close()


def out(resp):
    print(json.dumps(resp))
    sys.exit(0 if resp.get("ok") else 1)


def cli_start(args):
    # Check for existing running daemon
    if SOCK_PATH.exists():
        r = send({"cmd": "status"})
        if r.get("ok") and r.get("alive"):
            out({"ok": True, "action": "already_running", "pid": r.get("pid")})
        SOCK_PATH.unlink(missing_ok=True)

    SOCK_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [sys.executable, __file__, "_daemon"],
        cwd=Path(__file__).parent,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    line = proc.stdout.readline()
    if line:
        out(json.loads(line))
    else:
        err = ""
        try:
            err = LOG_FILE.read_text()[:300]
        except Exception:
            pass
        out({"ok": False, "error": f"daemon failed: {err}"})


def cli_stop(args):
    r = send({"cmd": "stop"})
    if PID_FILE.exists():
        try:
            os.kill(int(PID_FILE.read_text().strip()), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass
        PID_FILE.unlink(missing_ok=True)
    SOCK_PATH.unlink(missing_ok=True)
    out(r)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_daemon":
        run_daemon()
        return

    p = argparse.ArgumentParser(prog="vnc")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("status")

    s = sub.add_parser("screenshot", aliases=["ss"])
    s.add_argument("--out", "-o")
    s.add_argument("--format", "-f", default="jpeg", choices=["png", "jpeg", "jpg"])
    s.add_argument("--scale", "-s", type=float, default=0.5)
    s.add_argument("--quality", "-q", type=int, default=80)

    c = sub.add_parser("click")
    c.add_argument("x", type=float)
    c.add_argument("y", type=float)
    c.add_argument("--button", "-b", default="left", choices=["left", "right", "middle"])
    c.add_argument("--double", "-d", action="store_true")
    c.add_argument("--space", default="capture", choices=["native", "capture", "normalized", "n", "c"])

    m = sub.add_parser("move")
    m.add_argument("x", type=float)
    m.add_argument("y", type=float)
    m.add_argument("--space", default="capture", choices=["native", "capture", "normalized", "n", "c"])

    t = sub.add_parser("type")
    t.add_argument("text")

    k = sub.add_parser("key")
    k.add_argument("key")

    args = p.parse_args()
    {
        "start": cli_start, "stop": cli_stop,
        "status": lambda a: out(send({"cmd": "status"})),
        "screenshot": lambda a: out(send({"cmd": "screenshot", "out": a.out, "format": a.format,
                                           "scale": a.scale, "quality": a.quality})),
        "ss": lambda a: out(send({"cmd": "screenshot", "out": a.out, "format": a.format,
                                   "scale": a.scale, "quality": a.quality})),
        "click": lambda a: out(send({"cmd": "click", "x": a.x, "y": a.y,
                                      "button": a.button, "double": a.double, "space": a.space})),
        "move": lambda a: out(send({"cmd": "move", "x": a.x, "y": a.y, "space": a.space})),
        "type": lambda a: out(send({"cmd": "type", "text": a.text})),
        "key": lambda a: out(send({"cmd": "key", "key": a.key})),
    }[args.command](args)


if __name__ == "__main__":
    main()
