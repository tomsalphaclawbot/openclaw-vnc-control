# openclaw-vnc-control

A visual bridge for AI agents to control remote desktops via VNC.

## What it does

Captures screenshots and relays pointer/keyboard input over VNC. That's it. The tool is deliberately simple — all intelligence lives in the AI model analyzing the images.

## The loop

1. **Screenshot** → get an image of the remote desktop
2. **AI analyzes image** → determines where to click (x,y coordinates)
3. **Move/click** → send the action through VNC
4. **Screenshot** → verify the result
5. Repeat

## Why

AI agents can browse the web, run code, and call APIs — but they can't click permission dialogs, interact with native app UI, or handle system-level prompts. VNC gives them a universal visual control channel for anything on a screen.

## Setup

```bash
./setup.sh
source .venv/bin/activate
```

Or manually:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Set connection via environment:
```bash
export VNC_HOST=127.0.0.1
export VNC_PORT=5900
export VNC_PASSWORD=yourpass
export VNC_USERNAME=youruser  # for macOS ARD auth
```

Or pass as args (args override env):
```bash
python3 vnc-control.py --host 127.0.0.1 --port 5900 --password yourpass --username youruser screenshot
```

### Commands

```bash
# Check if host is reachable
python3 vnc-control.py status

# Test full VNC connection (connect, grab screen dimensions, disconnect)
python3 vnc-control.py connect

# Capture screenshot
python3 vnc-control.py screenshot                    # auto-generated path
python3 vnc-control.py screenshot --out screen.png   # explicit path

# Move pointer
python3 vnc-control.py move 500 300

# Click
python3 vnc-control.py click 500 300                         # left click
python3 vnc-control.py click 500 300 --button right          # right click
python3 vnc-control.py click 500 300 --double                # double click

# Type text
python3 vnc-control.py type "hello world"

# Send special keys
python3 vnc-control.py key enter
python3 vnc-control.py key tab
python3 vnc-control.py key ctrl-c
```

All commands return JSON:
```json
{
  "ok": true,
  "action": "screenshot",
  "image": {
    "path": "/tmp/vnc-control/screenshot-1234567890.png",
    "size_bytes": 9714780,
    "width": 3420,
    "height": 2214
  },
  "duration_s": 1.54
}
```

## Known limitations

- `key escape` can timeout on macOS ARD — other keys work fine
- Each command opens a new VNC connection (no persistent session yet)
- Uses vncdotool under the hood (Python/Twisted)

## Scope (v1)

- Single VNC host (not a fleet manager)
- CLI-first
- This is a bridge, not a platform

## Docs

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [ROADMAP.md](./ROADMAP.md)
- [TASKS.md](./TASKS.md)
