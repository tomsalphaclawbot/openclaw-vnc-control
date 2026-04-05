---
name: vnc-control
description: Control remote desktops via VNC for AI agent visual automation. Use when an AI agent needs to see, click, type, or interact with a remote desktop, native app, permission dialog, installer, or any GUI that APIs can't reach. Provides screenshot capture (PNG/JPEG with scaling), pointer move/click, keyboard type/key, lock screen detection, auto-unlock, and HTTP API mode for multi-agent/remote orchestration. Supports one-shot CLI (vnc-control.py), persistent session daemon (vnc), and HTTP API server (vnc_api.py) modes. Designed for the observe→decide→act→verify agent loop.
---

# VNC Control

Visual bridge for AI agents to control remote desktops via VNC. The tool captures screenshots and relays pointer/keyboard input — all intelligence lives in your vision analysis of the images.

## Modes

Three execution modes are available:

| Mode | Tool | When to use |
|------|------|-------------|
| **One-shot CLI** | `python3 vnc-control.py` | Quick scripts, single commands, no persistent state needed |
| **Session daemon** | `vnc` (wrapper) | Agent loops, keepalive, lock detection/unlock, faster repeated commands |
| **HTTP API server** | `python3 vnc_api.py` | Multi-agent orchestration, remote callers, programmatic automation over HTTP |

---

## Mandatory preflight (operator visibility)

Before **any** VNC bridge command (`vnc-control.py` or `vnc`), post a one-line preflight in the conversation first.

Required format:
- `Objective: <what this next VNC command is trying to accomplish>`

Rules:
- Do not run VNC commands without a preflight objective posted first.
- If the objective changes, post a new objective before the next VNC command.
- If 2 attempts fail on the same objective, post a blocker update before trying again.

---

## Setup

```bash
# From the project root
./setup.sh
source .venv/bin/activate

# Copy and fill credentials
cp .env.example .env
$EDITOR .env
```

Or manually: `pip install vncdotool Pillow`

## Connection credentials

Set via `.env` file (recommended) or environment:
```bash
export VNC_HOST=127.0.0.1
export VNC_PORT=5900
export VNC_PASSWORD=yourpass
export VNC_USERNAME=youruser  # required for macOS ARD
```

See `.env.example` for the full template.

CLI args (`--host`, `--port`, `--password`, `--username`) override env vars when passed.

---

## One-shot CLI (vnc-control.py)

### Efficiency profile for agents

Use `--profile ai` to hard-lock efficient defaults and avoid oversized image payloads:
- format forced to JPEG
- scale constrained to ≤ 0.6 (default 0.5)
- quality clamped to 40..85 (default 70)

### Agent loop example

```bash
TOOL="python3 vnc-control.py --profile ai"

# 1. Check connection
$TOOL status

# 2. Capture screen
$TOOL screenshot --out /tmp/screen.jpg

# 3. [Feed /tmp/screen.jpg to vision model → get coordinates]

# 4. Click target
$TOOL click 540 380

# 5. Type into focused field
$TOOL type "hello world"

# 6. Press enter
$TOOL key enter

# 7. Verify result
$TOOL screenshot --out /tmp/verify.jpg
```

### Commands

All commands return JSON with `"ok": true/false` and action metadata.

| Command | Usage | Notes |
|---------|-------|-------|
| `status` | `vnc-control.py [--profile ai] status` | TCP probe + RFB banner check |
| `connect` | `vnc-control.py [--profile ai] connect` | Full auth test, returns screen dimensions |
| `screenshot` | `vnc-control.py [--profile ai] screenshot [--out FILE] [--format png\|jpeg] [--scale 0.5] [--quality 80]` | Capture framebuffer |
| `click` | `vnc-control.py [--profile ai] click X Y [--space screenshot\|native\|normalized] [--button left\|right] [--double]` | Click + auto-verify screenshot |
| `move` | `vnc-control.py [--profile ai] move X Y [--space screenshot\|native\|normalized]` | Move pointer |
| `map` | `vnc-control.py map X Y --from screenshot --to native` | Convert coords programmatically |
| `type` | `vnc-control.py [--profile ai] type "text"` | Type text string |
| `key` | `vnc-control.py [--profile ai] key KEY` | Send special key (enter, tab, ctrl-c, etc.) |
| `click_element` | `vnc-control.py [--profile ai] click_element "Allow button" [--backend moondream\|gemma4\|anthropic\|remote]` | Natural-language targeting via vision model + click |

---

## Session Daemon (vnc)

The `vnc` wrapper launches a background Unix-socket daemon that maintains a persistent VNC connection, handles keepalive (prevents macOS screen lock during agent sessions), and exposes lock detection + auto-unlock.

### Start / stop

```bash
# Start daemon (reads from .env automatically)
vnc start

# Check daemon status
vnc status

# Stop daemon
vnc stop
```

### Daemon commands

All daemon commands return JSON. Same `--out`, `--format`, `--scale`, `--quality` options as the one-shot CLI.

| Command | Usage | Notes |
|---------|-------|-------|
| `start` | `vnc start` | Start background daemon |
| `stop` | `vnc stop` | Graceful shutdown |
| `status` | `vnc status` | Daemon PID + keepalive status |
| `screenshot` / `ss` | `vnc ss [--out FILE] [--scale 0.5]` | Capture framebuffer |
| `click` | `vnc click X Y [--space screenshot\|native\|normalized]` | Click + verify |
| `move` | `vnc move X Y` | Move pointer |
| `type` | `vnc type "text"` | Type text |
| `key` | `vnc key KEY` | Send special key |
| `detect-lock` | `vnc detect-lock [--screenshot FILE]` | Detect macOS lock screen |
| `unlock` | `vnc unlock --password PASS [--max-attempts N]` | Auto-unlock macOS lock screen |

### Lock detection

`detect-lock` uses a multi-signal heuristic against the current framebuffer:

1. **Mean luminance** — lock screen has a characteristic blurred/darkened range
2. **Center-card analysis** — login widget occupies a specific center-vertical band
3. **Arrow-button pixel probe** — submit arrow button appears at a fixed native coordinate

Returns JSON:
```json
{
  "ok": true,
  "locked": true,
  "confidence": 0.82,
  "signals": ["mean_lum=38 in lock range", "center_card darker than edges", "arrow_button pixel match"]
}
```

Threshold: `confidence >= 0.55` → locked.

### Auto-unlock

`unlock` executes a retry macro (up to `--max-attempts`, default 3):

1. Take screenshot + detect lock state
2. Click password field (native coords for macOS 3420×2214)
3. Clear field (Cmd+A → Delete)
4. Paste password via clipboard
5. Click submit arrow button; fallback to `key return` if needed
6. Re-detect lock — if confidence < 0.45, declare success
7. Wait and retry on failure

Returns JSON:
```json
{
  "ok": true,
  "unlocked": true,
  "attempts": 1,
  "method": "arrow_click"
}
```

**Important:** native coordinates for arrow button are tuned for a 3420×2214 screen (MacBook Air Retina). Different resolutions require coordinate adjustment.

### Keepalive

The daemon jiggles the pointer to the screen center every 25 seconds. This prevents macOS from engaging the screensaver or lock screen during long agent sessions.

**Prerequisites for stable keepalive:**
- Disable all hot corners (System Settings → Desktop & Dock → Hot Corners → set all to `-`)
- Set Lock Screen → "Require password after screen saver / sleep" to 1 hour minimum
- `pmset` AC displaysleep: `sudo pmset -c displaysleep 0` (prevent display sleep on AC)

---

## Screenshot sizing guide

| Format + Scale | Typical Size | Best for |
|----------------|-------------|----------|
| PNG full | ~10 MB | Pixel-precise work |
| JPEG full | ~1 MB | High-detail analysis |
| JPEG --scale 0.5 | ~360 KB | Default for agent loops (readable by vision models) |
| JPEG --scale 0.25 | ~110 KB | Quick status checks |

Prefer `--format jpeg --scale 0.5` for agent loops — all text and UI elements remain readable.

---

## Important notes

- **macOS ARD** requires `--username` (Apple Remote Desktop uses username+password auth, not plain VNC password)
- `key escape` may timeout on macOS ARD — all other keys work reliably
- One-shot CLI opens a new VNC connection per command; daemon mode maintains a persistent session
- Click automatically captures a verification screenshot (returned in JSON as `verify_image`)
- `click_element` includes objective state-change verification (`verification.change_pct`) and optional retry-on-no-change controls (`--verify-retries`, `--retry-offset`, `--require-state-change`)
- Default coordinate input space is **screenshot space**; translation to native is automatic
- For agent runs, prefer daemon mode + `--scale 0.5` for efficient capture
- Lock/unlock native coordinates are calibrated for 3420×2214 (MacBook Air); adjust for other resolutions

---

## HTTP API Server (vnc_api.py)

The HTTP API wraps all CLI commands in a FastAPI server, making the VNC bridge callable over HTTP from any agent, service, or remote orchestrator.

### Start the server

```bash
# Default: 127.0.0.1:7472, no auth
python3 vnc_api.py

# Custom port + bind + optional shared secret
python3 vnc_api.py --port 8080 --bind 0.0.0.0

# With auth (recommended for non-localhost)
VNC_API_SECRET=mysecret python3 vnc_api.py
```

### Authentication

Set `VNC_API_SECRET` in the environment. When set, all POST requests must include:
```
X-VNC-API-Secret: <your-secret>
```
Requests without a valid secret return `403 Forbidden`.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/status` | Health check + VNC connection probe |
| `POST` | `/screenshot` | Capture framebuffer → returns base64 JPEG in JSON |
| `POST` | `/click` | Click at (x, y) |
| `POST` | `/move` | Move pointer to (x, y) |
| `POST` | `/type` | Type a text string |
| `POST` | `/key` | Send a keypress (enter, tab, ctrl-c, etc.) |

### Example requests

```bash
# Status
curl http://127.0.0.1:7472/status

# Screenshot (returns base64 image + metadata)
curl -X POST http://127.0.0.1:7472/screenshot \
  -H "Content-Type: application/json" \
  -d '{"scale": 0.5, "quality": 70}'

# Click
curl -X POST http://127.0.0.1:7472/click \
  -H "Content-Type: application/json" \
  -d '{"x": 540, "y": 380}'

# Type
curl -X POST http://127.0.0.1:7472/type \
  -H "Content-Type: application/json" \
  -d '{"text": "hello world"}'

# Key
curl -X POST http://127.0.0.1:7472/key \
  -H "Content-Type: application/json" \
  -d '{"key": "return"}'
```

### Response shape

All endpoints return JSON:
```json
{
  "ok": true,
  "image": "<base64-encoded-jpeg>",   // screenshot/click only
  "width": 1710,                       // screenshot only
  "height": 1107,                      // screenshot only
  "scale": 0.5
}
```

Errors return `{"ok": false, "error": "<message>"}` with an appropriate HTTP status code.

### Prerequisites

```bash
pip install fastapi uvicorn
```

Or run `./setup.sh` which installs all dependencies.

---

## Troubleshooting

- **Connection refused**: verify VNC/Screen Sharing is enabled on the target and the port is correct
- **Auth failed**: for macOS, ensure you're using `--username` with the macOS account name
- **Timeout on key**: append a screenshot after key events as a workaround (the tool does this automatically for most keys)
- **Daemon won't start**: check `.env` has all four vars set; run `vnc status` to see error output
- **Lock detection wrong**: use `vnc detect-lock --screenshot /tmp/snap.jpg` to capture and manually inspect — calibrate luminance/pixel thresholds in `vnc-session.py` if needed
- **Unlock fails**: ensure `VNC_PASSWORD` is set in `.env`; verify arrow-button native coords match your screen resolution
- **API server 403**: ensure `VNC_API_SECRET` env matches the `X-VNC-API-Secret` header sent by callers
- **API server not found**: check port (default 7472); use `--bind 0.0.0.0` only when remote access is needed
