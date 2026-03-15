# openclaw-vnc-control — Architecture

## What this is

A **visual bridge** between an AI agent and a VNC desktop. The tool is deliberately dumb — it captures pixels and relays pointer/keyboard input. All intelligence lives in the AI model analyzing the screenshots.

## The loop

```
┌─────────────┐
│  Screenshot  │──→ JPEG image (350KB @ 50%)
└──────┬───────┘
       │
       ▼
┌─────────────┐
│  AI Vision   │──→ "click at x=540, y=380"
└──────┬───────┘
       │
       ▼
┌─────────────┐
│  Move/Click  │──→ VNC pointer event
└──────┬───────┘
       │
       ▼
┌─────────────┐
│  Screenshot  │──→ verify result
└─────────────┘
       │
       └──→ repeat
```

The tool handles steps 1, 3, 4. Step 2 is the AI agent's job.

## Two-mode Design

### v1: `vnc-control.py` (standalone)
- Each command = fresh `vncdo` subprocess = fresh VNC connection
- ~1.3s per command (connect + action + disconnect)
- No state between commands
- Simple, reliable, no dependencies beyond vncdo

### v2: `vnc-session.py` (daemon + CLI)
- Daemon process listens on Unix socket (`/tmp/vnc-session/vnc.sock`)
- Client (`vnc` wrapper) sends JSON commands to daemon
- Daemon dispatches via fresh `vncdo` subprocess per command (same as v1)
- Daemon adds: keepalive jiggle, coordinate space tracking, state persistence

### Why not persistent VNC connections?

Tested and abandoned:
- **vncdotool threaded API** (`api.connect()`): `captureScreen` times out waiting for macOS ARD framebuffer response
- **asyncvnc**: Connects fine, keyboard/mouse work, but screenshots return all-black framebuffer (0 non-zero pixels). Only supports Raw and ZLib encodings.
- **vncdo stdin mode** (`vncdo -`): Processes all commands then exits on stdin close. Can't interleave commands with reads.

Subprocess-per-command is ~1.3s and 100% reliable. Good enough.

## Components

### VNC Connection Layer
- Uses `vncdo` CLI from vncdotool (Python/Twisted)
- Auth: password (standard VNC) or username+password (macOS ARD/Apple Remote Desktop)
- Connection config: `.env` file → env vars → CLI args (precedence: args > env)
- vncdo found via: project `.venv/bin/vncdo` first, then PATH

### Screen Capture
- Raw capture: vncdo outputs PNG at native resolution
- Post-processing: PIL/Pillow for JPEG conversion + scaling
- Default: JPEG, 50% scale, quality 80 → ~350KB for 3420×2214 screen
- `--nocursor` flag strips hardware cursor from captures

### Input Relay
- Pointer: `move X Y`, `click BUTTON`
- Keyboard: `type TEXT`, `key KEYNAME`
- Key combos: `key ctrl-c`, `key shift-1`, `key super_l-a` (macOS cmd)
- ARD workaround: key/move commands append throwaway `capture` to force framebuffer update and prevent hang

### Coordinate System
Three spaces, auto-converted by daemon:
- **native**: raw screen resolution (e.g., 3420×2214)
- **capture**: screenshot image coordinates (e.g., 1710×1107 at 50% scale)
- **normalized**: 0.0-1.0 fraction of screen

Conversion: `capture_coord / scale = native_coord`

### Keepalive (daemon only)
- 25-second interval mouse jiggle in center of screen
- **CRITICAL**: jiggle MUST avoid screen corners (macOS hot corners trigger sleep/lock)
- Previous bug: jiggle to (1,1) hit top-left hot corner → put display to sleep → lock

## macOS ARD Quirks (documented)

| Issue | Workaround |
|-------|-----------|
| `key escape` timeout | Append flush `capture` after key commands |
| Hot corner triggers lock | Keepalive jiggles center area only |
| `!` char unreliable in `type` | Use `key shift-1` or `--force-caps` |
| `key return` intermittent on lock screen | Under investigation — may need click on submit arrow instead |
| Screen locks in ~1-2 min | Daemon keepalive helps but doesn't fully prevent |
| Persistent API connections hang | Use subprocess-per-command instead |
| asyncvnc black screenshots | Library only supports Raw/ZLib, macOS needs other encodings |

## Connection Config (v1)

Single host only. Credentials via:
- `.env` file in project root (gitignored)
- Env vars: `VNC_HOST`, `VNC_PORT`, `VNC_PASSWORD`, `VNC_USERNAME`
- CLI args: `--host`, `--port`, `--password`, `--username`
- Args override env, env overrides .env file

## Non-goals (v1)
- AI/vision analysis (that's the caller's job)
- Multi-host management
- Clipboard/audio sync
- Web UI
- Persistent VNC connection pooling (proven unreliable with macOS ARD)

## File Map

```
vnc-control.py     — v1 standalone CLI (each command = fresh connection)
vnc-session.py     — v2 daemon + CLI client
vnc                — shell wrapper (resolves symlinks, activates venv)
.env               — VNC credentials (gitignored, never committed)
.env.example       — template for credentials
setup.sh           — one-command project setup
requirements.txt   — Python dependencies (vncdotool, Pillow)
skill/             — OpenClaw/AgentSkill package
  SKILL.md         — agent-facing skill doc
  scripts/         — install.sh, agent-loop-example.sh
```
