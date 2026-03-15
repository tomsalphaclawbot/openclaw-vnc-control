# openclaw-vnc-control — Architecture (Planning v0)

## Purpose
Build a small, reliable **drive-by-wire control core** for VNC sessions that supports:
1. connect/authenticate
2. screen capture
3. pointer move
4. click

CLI-first implementation, then API wrapper.

The operating model is explicit:
- **CLI = actuator + sensor surface** (executes commands, returns observations)
- **AI agent = decision layer** (interprets results, chooses next command)

---

## Design Principles
- **Protocol-adapter over protocol-rewrite**: rely on a mature VNC/RFB client library first.
- **Deterministic control primitives**: actions must be observable and testable.
- **Session-centric model**: explicit connect/disconnect lifecycle.
- **Fail loudly**: return structured errors with actionable context.
- **Composable**: primitives can be orchestrated by any agent runtime.

---

## High-Level Component Model

### 1) Transport Layer
Responsibilities:
- Establish TCP connection to VNC endpoint
- Negotiate RFB protocol version/encodings
- Handle authentication
- Receive framebuffer updates

Outputs:
- connected session stream
- decoded framebuffer frames

### 2) Session Layer
Responsibilities:
- Session lifecycle (`create`, `ready`, `degraded`, `closed`)
- Timeouts, heartbeat, reconnect policy
- Shared state (screen dimensions, cursor position if known)

Outputs:
- stable session handle / session id

### 3) Screen Layer
Responsibilities:
- Snapshot current framebuffer
- Export to PNG/JPEG
- Optional crop region (`x,y,w,h`)

Outputs:
- image bytes/file path + metadata (width/height/timestamp)

### 4) Input Layer
Responsibilities:
- Pointer movement events
- Button events (left/right/middle)
- Click abstractions (single/double)

Outputs:
- action result + post-action cursor coordinates

### 5) Control Interfaces
Responsibilities:
- CLI commands for human/operator use
- CLI contracts optimized for AI-agent planning loops
- Local API (HTTP/WebSocket) for programmatic use (phase 2)

Outputs:
- JSON response envelopes, artifact paths, and exit codes

---

## Drive-by-Wire Interaction Contract

The system should support a simple agent loop:
1. `observe` (capture current screen + metadata)
2. `decide` (external AI chooses next action)
3. `act` (CLI executes pointer/click command)
4. `verify` (capture next frame and return result)

### Required response data per command
- `ok` / `error`
- `sessionId`
- `timestamp`
- `screen` metadata (`width`, `height`, optional cursor)
- `artifacts` (e.g. screenshot path)
- optional `nextHints` for retries/recovery

---

## Command Surface (MVP)

### Session
- `connect --host --port --password`
- `disconnect`
- `status`

### Screen
- `screenshot --out <path> [--crop x,y,w,h]`
- `observe --out <path>` (alias/shortcut optimized for agent loops)

### Input
- `move --x <int> --y <int>`
- `click --x <int> --y <int> [--button left|right|middle] [--double]`

---

## Data Contracts (Initial)

### Success envelope
```json
{
  "ok": true,
  "sessionId": "sess_abc123",
  "timestamp": "2026-03-15T09:12:00Z",
  "screen": {
    "width": 1920,
    "height": 1080
  },
  "artifacts": {
    "screenshot": "/tmp/vnc/frame-001.png"
  },
  "result": {
    "action": "click",
    "x": 540,
    "y": 380
  }
}
```

### Error envelope
```json
{
  "ok": false,
  "sessionId": "sess_abc123",
  "error": {
    "code": "AUTH_FAILED",
    "message": "VNC authentication failed",
    "retryable": false
  }
}
```

---

## Reliability Baseline
- Operation timeout defaults per command
- Bounded retries on connect only
- Idempotent disconnect
- Structured logs with session correlation id

---

## Security Baseline
- Never log passwords/secrets
- Support env var injection for secrets
- Localhost-only API bind by default (phase 2)

---

## Non-Goals (v1)
- Full autonomous planning/vision stack
- Rich web UI
- Multi-monitor advanced composition
- Audio/clipboard sync

---

## Open Decisions
1. Primary language/runtime (Node vs Python vs Go)
2. VNC library selection
3. API transport shape for phase 2 (REST vs WebSocket-first)
4. Screenshot format defaults and compression strategy
