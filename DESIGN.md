# Design: AI Agent Host Control via VNC

**Status:** Draft v1 (2026-04-04)  
**Scope:** Architecture and principles for open-source multi-agent deployment

---

## Problem

AI agents can call APIs, write files, run code — but they can't interact with native GUI surfaces: permission dialogs, system prompts, app UIs, anything that requires a human to click. This is a real wall. VNC gives agents a visual control channel for anything on a screen.

The goal: a clean, safe, well-documented tool that **any** AI agent framework can use to control its host machine, when explicitly given permission by a human operator.

---

## Design Principles

### 1. Permission is explicit, not ambient

The human operator configures the tool. The agent uses it. Never the reverse.

A **permission manifest** (`vnc-permissions.json`) defines exactly what the agent is allowed to do:
- Which coordinate regions are clickable (whitelist zones)
- Which key sequences are allowed
- Whether the agent can take screenshots freely or only on request
- Rate limits (actions/minute)
- Whether a human-readable audit log is required

Default when no manifest: **read-only** (screenshots only, no input).

### 2. Every action is auditable

All commands write to a structured action log (`~/.vnc-control/audit.jsonl`). Log includes:
- Timestamp, agent ID, action type
- For clicks: screenshot before + after, coords, detection result
- For types: character count only (not content, for privacy)
- Success/failure + elapsed time

The log is append-only from the agent's perspective. Human can review any action.

### 3. Vision backend is pluggable

The detection layer (`detect_element()`) is the stable interface. Backends are swappable:
- **Local**: Moondream2, Gemma4, Florence-2, any mlx/transformers model
- **Remote**: Anthropic, OpenAI vision, any compatible API
- **Future**: fine-tuned UI grounding models (SeeClick, OmniParser, etc.)

All backends return the same canonical `DetectionResult`. Adding a backend = implement `_detect_<name>(image_path, query) → DetectionResult`.

### 4. Auth is standard environment variables

No framework-specific auth parsing. The tool reads:
- `ANTHROPIC_API_KEY` — Anthropic vision backend
- `OPENAI_API_KEY` — OpenAI vision backend  
- `VNC_HOST`, `VNC_PORT`, `VNC_USERNAME`, `VNC_PASSWORD` — VNC connection

Credentials are never logged, never in output JSON, never in error messages.

### 5. Coordinate system is explicit and documented

Every output includes the coordinate space:
```json
{
  "box":          {"x_min": 100, "y_min": 50, "x_max": 200, "y_max": 80},
  "box_norm":     {"x_min": 0.058, "y_min": 0.045, "x_max": 0.117, "y_max": 0.072},
  "center":       {"x": 150, "y": 65},
  "center_norm":  {"x": 0.087, "y": 0.058},
  "image_size":   [1710, 1107],
  "capture_scale": 0.5,
  "native_coords": {"x": 300, "y": 130}
}
```

`native_coords` is always the VNC click target. Everything else is informational.

### 6. Platform differences are explicit, not hidden

macOS-specific behavior (ARD auth, TCC dialogs, key aliases) is clearly labeled and isolated. The core screenshot → detect → click pipeline is platform-agnostic. Platform quirks are documented in `docs/platforms/`.

### 7. CLI-first, library-second

The primary interface is JSON-output CLI — works with any agent framework that can run a subprocess and parse stdout. A Python library wrapper (`vnc_control.py` importable module) is a secondary interface for tighter integrations.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     AI Agent (any)                      │
│  OpenClaw / Hermes / Codex / custom / your framework    │
└──────────────────────┬──────────────────────────────────┘
                       │  subprocess + JSON
                       ▼
┌─────────────────────────────────────────────────────────┐
│                   vnc-control CLI                       │
│                                                         │
│  Permission Gate → checks vnc-permissions.json          │
│  Action Logger  → writes audit.jsonl                    │
│                                                         │
│  Commands:                                              │
│    screenshot   → capture image                         │
│    find_element → detect element, return coords         │
│    click_element → detect + click                       │
│    click x y   → direct coord click                     │
│    type text   → keyboard input                         │
│    key name    → key press                              │
└──────┬──────────────────────────────────────────────────┘
       │
       ├── VNC Layer (vncdo / vncdotool)
       │     Handles: connect, capture, move, click, key
       │     Platform: macOS ARD, Linux VNC, any VNC server
       │
       └── Vision Layer (detect_element)
             │
             ├── moondream  (local, MPS/CPU, ~5s, no cost)
             ├── gemma4     (local server, OpenAI-compat, ~5s, no cost)
             ├── florence2  (local, fast CPU inference, TODO)
             └── anthropic  (remote, best reasoning, API cost)
```

---

## DetectionResult Schema (canonical, stable)

This is the contract between vision backends and callers. **Never break this.**

```json
{
  "found":       true,
  "query":       "Allow button",
  "backend":     "moondream",
  "image_size":  [1710, 1107],
  "capture_scale": 0.5,

  "box": {
    "x_min": 1177, "y_min": 187,
    "x_max": 1241, "y_max": 224
  },
  "box_norm": {
    "x_min": 0.688304, "y_min": 0.168925,
    "x_max": 0.725731, "y_max": 0.202349
  },
  "center":      {"x": 1209, "y": 205},
  "center_norm": {"x": 0.707018, "y": 0.185185},
  "confidence":  "high",
  "note":        "optional model reasoning",
  "elapsed_s":   6.863
}
```

When `found: false`:
```json
{
  "found":    false,
  "query":    "Submit button",
  "backend":  "gemma4",
  "note":     "No element matching description is visible",
  "elapsed_s": 4.2
}
```

---

## Permission Manifest (`vnc-permissions.json`)

```json
{
  "version": 1,
  "agent_id": "hermes-main",
  "granted_by": "tom@example.com",
  "granted_at": "2026-04-04T00:00:00Z",

  "permissions": {
    "screenshot": true,
    "click": true,
    "type": true,
    "key": true,
    "find_element": true,
    "click_element": true
  },

  "restrictions": {
    "rate_limit_actions_per_minute": 60,
    "click_regions": null,
    "blocked_keys": ["cmd-q", "ctrl-alt-delete"],
    "require_audit_log": true
  }
}
```

`click_regions: null` = no restriction. Otherwise: array of `{x_min, y_min, x_max, y_max}` in normalized coords.

---

## Integration Guide (for agent framework developers)

### Minimal usage (any agent, any language)

```bash
# 1. Set credentials
export VNC_HOST=127.0.0.1
export VNC_PORT=5900
export VNC_USERNAME=myuser
export VNC_PASSWORD=mypassword
export ANTHROPIC_API_KEY=sk-ant-...  # for remote vision (optional)

# 2. Take a screenshot
python3 vnc-control.py screenshot --out /tmp/screen.jpg

# 3. Find an element
python3 vnc-control.py find_element "Submit button"
# → JSON with box, center, native_coords

# 4. Click an element by description
python3 vnc-control.py click_element "Allow button" --backend moondream
# → JSON with detection + native_coords + ok status
```

All output is JSON on stdout. Exit code 0 = ok, non-zero = error.

### Python library usage

```python
from vnc_control import VNCClient

client = VNCClient(host="127.0.0.1", port=5900,
                   username="user", password="pass")

# Screenshot
img_path = client.screenshot()

# Detect element
result = client.find_element("Allow button", backend="moondream")
print(result["center"])  # {"x": 1209, "y": 205}

# Click element
result = client.click_element("Allow button", backend="gemma4")
```

### Agent loop pattern

```python
for step in agent_steps:
    # 1. Observe
    screenshot = client.screenshot()
    
    # 2. Decide (your LLM call)
    action = llm.decide(screenshot, task)
    
    # 3. Act
    if action.type == "click":
        client.click_element(action.target, backend="moondream")
    elif action.type == "type":
        client.type(action.text)
    
    # 4. Verify (screenshot again, check state changed)
    after = client.screenshot()
```

---

## Roadmap

### Done ✅
- Core VNC: screenshot, click, type, key
- Coord system: screenshot / native / normalized spaces, auto-conversion
- Vision backends: Moondream2 (local), Gemma4 (local server), Anthropic (remote)
- Canonical DetectionResult schema (2026-04-04)
- Sprint H: click_element command with multi-backend support

### Next
- [ ] Permission manifest (`vnc-permissions.json`) enforcement
- [ ] Audit log (`audit.jsonl`) 
- [ ] Florence-2 local backend (fast CPU, no GPU required)
- [ ] Python library interface (`from vnc_control import VNCClient`)
- [ ] `agent_id` flag — all output tagged with calling agent
- [ ] Remove OpenClaw-specific auth parsing from backends
- [ ] Platform docs: macOS setup, Linux VNC setup
- [ ] Multi-agent safety: session locking (only one agent controls at a time)

### Future
- [ ] SeeClick / OmniParser backend (UI-specialized grounding)
- [ ] Region-based click restriction enforcement
- [ ] Rate limiter
- [ ] Web dashboard for audit log review
- [ ] Hermes integration guide

---

## What This Is Not

- Not a general browser automation tool (use Playwright/Puppeteer for that)
- Not a security tool — VNC credentials must already be set up by a human
- Not safe for untrusted agents — permission manifest gates actions but doesn't sandbox the OS
- Not a replacement for native accessibility APIs where those exist

The right mental model: **a controlled visual keyboard and mouse for agents**, equivalent to sitting a human in front of a screen but with explicit permission controls and full audit trail.
