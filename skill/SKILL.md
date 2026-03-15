---
name: vnc-control
description: Control remote desktops via VNC for AI agent visual automation. Use when an AI agent needs to see, click, type, or interact with a remote desktop, native app, permission dialog, installer, or any GUI that APIs can't reach. Provides screenshot capture (PNG/JPEG with scaling), pointer move/click, keyboard type/key, and connection status checking. Designed for the observe→decide→act→verify agent loop where the AI analyzes screenshots to determine coordinates.
---

# VNC Control

Visual bridge for AI agents to control remote desktops via VNC. The tool captures screenshots and relays pointer/keyboard input — all intelligence lives in your vision analysis of the images.

## Setup

```bash
# Run from the skill directory
cd "$(dirname "$0")/.."
./setup.sh
source .venv/bin/activate
```

Or manually: `pip install vncdotool Pillow`

## Connection

Set via environment (recommended):
```bash
export VNC_HOST=127.0.0.1
export VNC_PORT=5900
export VNC_PASSWORD=yourpass
export VNC_USERNAME=youruser  # required for macOS ARD
```

Or pass as CLI args (`--host`, `--port`, `--password`, `--username`). Args override env.

## Agent Loop

The core workflow for visual desktop automation:

1. **Screenshot** → capture current screen state
2. **Analyze** → use vision model to identify UI elements and determine coordinates
3. **Act** → move/click/type at the identified coordinates
4. **Verify** → screenshot again to confirm the action worked
5. **Repeat** until task is complete

### Step-by-step example

```bash
TOOL="python3 vnc-control.py"

# 1. Check connection
$TOOL status

# 2. Capture screen (JPEG at 50% for fast AI analysis)
$TOOL screenshot --format jpeg --scale 0.5 --out /tmp/screen.jpg

# 3. [Feed /tmp/screen.jpg to vision model, get coordinates]

# 4. Click where the model says
$TOOL click 540 380

# 5. Type into the focused field
$TOOL type "hello world"

# 6. Press enter
$TOOL key enter

# 7. Verify with another screenshot
$TOOL screenshot --format jpeg --scale 0.5 --out /tmp/verify.jpg
```

## Commands

All commands return JSON with `"ok": true/false` and action metadata.

| Command | Usage | Notes |
|---------|-------|-------|
| `status` | `vnc-control.py status` | TCP probe + RFB banner check |
| `connect` | `vnc-control.py connect` | Full auth test, returns screen dimensions |
| `screenshot` | `vnc-control.py screenshot [--out FILE] [--format png\|jpeg] [--scale 0.5] [--quality 80]` | Capture framebuffer |
| `click` | `vnc-control.py click X Y [--button left\|right] [--double]` | Click + auto-verify screenshot |
| `move` | `vnc-control.py move X Y` | Move pointer |
| `type` | `vnc-control.py type "text"` | Type text string |
| `key` | `vnc-control.py key KEY` | Send special key (enter, tab, ctrl-c, etc.) |

## Screenshot sizing guide

| Format + Scale | Typical Size | Best for |
|----------------|-------------|----------|
| PNG full | ~10 MB | Pixel-precise work |
| JPEG full | ~1 MB | High-detail analysis |
| JPEG --scale 0.5 | ~360 KB | Default for agent loops (readable by vision models) |
| JPEG --scale 0.25 | ~110 KB | Quick status checks |

Prefer `--format jpeg --scale 0.5` for agent loops — all text and UI elements remain readable.

## Important notes

- **macOS ARD** requires `--username` (Apple Remote Desktop uses username+password auth, not plain VNC password)
- `key escape` may timeout on macOS ARD — all other keys work reliably
- Each command opens a new VNC connection (no persistent session yet)
- Click automatically captures a verification screenshot (returned in JSON as `verify_image`)
- Screen coordinates are in native resolution (check `connect` output for `screen_width`/`screen_height`)

## Troubleshooting

- **Connection refused**: verify VNC/Screen Sharing is enabled on the target and the port is correct
- **Auth failed**: for macOS, ensure you're using `--username` with the macOS account name
- **Timeout on key**: append a screenshot after key events as a workaround (the tool does this automatically for most keys)
