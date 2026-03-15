# openclaw-vnc-control

A visual bridge for AI agents to control remote desktops via VNC.

## What it does

Captures screenshots and relays pointer/keyboard input over VNC. The tool is deliberately simple — all intelligence lives in the AI model analyzing the images.

## The loop

1. **Screenshot** → get an image of the remote desktop
2. **AI analyzes image** → determines where to click (x,y coordinates)
3. **Move/click** → send the action through VNC
4. **Screenshot** → verify the result
5. Repeat

## Why

AI agents can browse the web, run code, and call APIs — but they can't click permission dialogs, interact with native app UI, or handle system-level prompts. VNC gives them a universal visual control channel for anything on a screen.

## Architecture

Two modes:

- **`vnc-control.py`** — v1 standalone CLI. Each command opens a fresh VNC connection (~1.3s). Simple, reliable, no daemon.
- **`vnc-session.py`** (v2) — session daemon + thin CLI wrapper. Daemon provides keepalive (prevents macOS screen lock), coordinate space tracking, and dispatches commands via `vncdo` subprocess. Client talks to daemon over Unix socket.

Both use `vncdo` (vncdotool) under the hood. Persistent VNC API connections (vncdotool threaded API, asyncvnc) were tested but hit macOS ARD framebuffer-hang issues — subprocess-per-command is the proven reliable path.

## Quick Start

```bash
# Setup
./setup.sh
source .venv/bin/activate

# Configure credentials
cp .env.example .env   # edit with your VNC host/port/user/pass

# v2 daemon (recommended)
vnc start              # start daemon with keepalive
vnc ss                 # screenshot (jpeg, 50% scale, ~350KB)
vnc click 500 300      # click at capture-space coords
vnc type "hello"       # type text
vnc key return         # send key
vnc stop               # stop daemon

# Or v1 standalone (no daemon needed)
python3 vnc-control.py --profile ai screenshot          # efficient defaults locked (jpeg, 0.5, q70)
python3 vnc-control.py --profile ai click 1000 600     # screenshot-space by default
python3 vnc-control.py map 1000 600 --from screenshot --to native
```

## Connection Config

Credentials via `.env` file, env vars, or CLI args (args override env):

```bash
# .env file or shell env:
VNC_HOST=127.0.0.1
VNC_PORT=5900
VNC_USERNAME=youruser    # required for macOS ARD auth
VNC_PASSWORD=yourpass

# Or CLI args (v1 only):
python3 vnc-control.py --host 127.0.0.1 --port 5900 --username user --password pass screenshot
```

## v1 AI Profile (efficiency mode)

Use `--profile ai` to hard-lock efficient capture defaults and avoid oversized images:

- format forced to JPEG (PNG requests are normalized to JPEG)
- scale constrained to <= 0.6 (defaults to 0.5)
- quality clamped to 40..85 (defaults to 70)
- coordinate translation remains automatic (`screenshot` / `native` / `normalized` spaces)

Examples:

```bash
python3 vnc-control.py --profile ai screenshot
python3 vnc-control.py --profile ai click 640 420 --space screenshot
python3 vnc-control.py --profile ai click 0.5 0.38 --space normalized
python3 vnc-control.py map 640 420 --from screenshot --to native
```

## v2 Daemon Commands (`vnc`)

The `vnc` wrapper script auto-activates the venv and resolves paths through symlinks.

```bash
vnc start                           # start daemon (keepalive + coordinate tracking)
vnc stop                            # stop daemon
vnc status                          # daemon health check

vnc screenshot                      # jpeg, 50% scale (default)
vnc ss                              # alias for screenshot
vnc ss -o /tmp/screen.jpg           # explicit output path
vnc ss --format png --scale 1.0     # full-res PNG
vnc ss --quality 60                 # lower quality = smaller file

vnc click 500 300                   # click at capture-space coords (default)
vnc click 0.5 0.3 --space n        # normalized coords (0.0-1.0)
vnc click 1000 600 --space native   # native resolution coords
vnc click 500 300 --button right    # right-click
vnc click 500 300 --double          # double-click

vnc move 500 300                    # move pointer
vnc type "hello world"              # type text
vnc key return                      # send key press
vnc key tab                         # tab
vnc key ctrl-c                      # key combo
```

All commands return JSON:
```json
{
  "ok": true,
  "path": "/tmp/vnc-session/captures/screen-1234567890.jpg",
  "native_w": 3420, "native_h": 2214,
  "capture_w": 1710, "capture_h": 1107,
  "scale": 0.5,
  "size_kb": 350,
  "duration_s": 0.65
}
```

## Coordinate Spaces

The daemon tracks three coordinate spaces and auto-converts:

| Space | Description | Example |
|-------|-------------|---------|
| `capture` (default) | Coordinates in screenshot image space | `vnc click 500 300` |
| `native` | Raw screen resolution coords | `vnc click 1000 600 --space native` |
| `normalized` | 0.0-1.0 fraction of screen | `vnc click 0.5 0.3 --space n` |

With default 50% scale: capture coords are automatically doubled for native resolution (e.g., capture 500,300 → native 1000,600).

## Screenshot Size Comparison

| Format | Scale | Typical Size | Use Case |
|--------|-------|-------------|----------|
| PNG | 1.0 | ~10 MB | Pixel-perfect archival |
| JPEG | 1.0 | ~1 MB | Full-res, good enough for AI |
| JPEG | 0.5 | ~350 KB | **Default — ideal for AI vision** |
| JPEG | 0.25 | ~110 KB | Bandwidth-constrained |

## Known Issues & Lessons

### macOS ARD Specific
- **`key escape` times out** — macOS ARD doesn't send framebuffer update after Escape. Workaround: flush capture appended to key commands.
- **Hot corners trigger lock** — keepalive mouse jiggle must avoid screen corners. Center-area jiggle is safe.
- **`!` character in type command** — vncdotool may handle special chars inconsistently. Use `--force-caps` or `key shift-1` for reliable `!`.
- **Lock screen submit** — `key return` after password entry is intermittently unreliable on ARD. Under investigation.
- **Screen lock timing** — macOS locks aggressively (~1-2 min). Daemon keepalive (25s jiggle interval) helps but doesn't fully prevent lock.

### General
- Each command opens a new VNC connection (~1.3s overhead). The daemon mitigates this with keepalive but doesn't pool connections.
- Persistent API connections (vncdotool threaded API, asyncvnc) were tested and abandoned due to macOS ARD framebuffer issues (black screenshots, timeout hangs).

## Scope (v1)

- Single VNC host (not a fleet manager)
- CLI-first, API later
- This is a bridge, not a platform

## For AI Agents

This project includes a ready-to-use [OpenClaw/AgentSkill](./skill/SKILL.md). Any AI agent can:

1. Clone this repo
2. Run `skill/scripts/install.sh` (sets up Python venv + dependencies)
3. Read `skill/SKILL.md` for full usage instructions
4. Start the observe→decide→act→verify loop

## Docs

- [ARCHITECTURE.md](./ARCHITECTURE.md) — design decisions and component model
- [ROADMAP.md](./ROADMAP.md) — phased delivery plan
- [TASKS.md](./TASKS.md) — current sprint status and known issues
