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

## Scope (v1)

- Single VNC host (not a fleet manager)
- CLI-first
- Credentials via args (`--host`, `--port`, `--password`) or env (`VNC_HOST`, `VNC_PORT`, `VNC_PASSWORD`)
- This is a bridge, not a platform

## Status

Planning complete. Next: technical spike for library/runtime selection.

## Docs

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [ROADMAP.md](./ROADMAP.md)
- [TASKS.md](./TASKS.md)
