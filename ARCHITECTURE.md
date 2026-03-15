# openclaw-vnc-control — Architecture

## What this is

A **visual bridge** between an AI agent and a VNC desktop. The tool is deliberately dumb — it captures pixels and relays pointer/keyboard input. All intelligence lives in the AI model analyzing the screenshots.

## The loop

```
┌─────────────┐
│  Screenshot  │──→ image file
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

1. **Screenshot** — capture current framebuffer as an image file (PNG)
2. **AI vision** — external model analyzes image, determines x,y coordinates
3. **Move/click** — send pointer/keyboard actions through VNC
4. **Screenshot** — verify the result
5. Repeat

The tool handles steps 1, 3, 4. Step 2 is the AI agent's job.

## Components

### VNC Connection
- TCP connect to VNC host
- RFB protocol negotiation
- Authentication (password)
- Receive framebuffer updates

### Screen Capture
- Grab current framebuffer
- Save as PNG (default) or JPEG
- Optional crop region
- Return file path + dimensions

### Input Relay
- Pointer move (x, y)
- Mouse button press/release (left/right/middle, single/double click)
- Keyboard input (key press, type text)

### CLI
- `connect` — establish VNC session
- `screenshot` — capture screen → image file
- `move` — move pointer to x,y
- `click` — click at x,y
- `type` — send keystrokes
- `disconnect` — close session

## Connection config (v1)

Single host only. Credentials via:
- CLI args: `--host`, `--port`, `--password`
- Env vars: `VNC_HOST`, `VNC_PORT`, `VNC_PASSWORD`
- Args override env

## Non-goals (v1)
- AI/vision analysis (that's the caller's job)
- Multi-host management
- Clipboard/audio sync
- Web UI
- Rich structured response envelopes (images are the primary output)

## Open decisions
1. Language/runtime (Node.js vs Python)
2. VNC client library
