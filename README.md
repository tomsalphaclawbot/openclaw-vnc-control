# openclaw-vnc-control

Public project for reliable VNC control workflows with OpenClaw.

## Mission
Ship a tiny but meaningful improvement to how agents control and recover remote desktop sessions.

## Core capabilities (MVP)
- Connect to a VNC host
- Capture screen output
- Move pointer
- Click UI elements

## Drive-by-wire model
This project is intentionally built as a **drive-by-wire CLI** for AI agents:
- CLI returns machine-readable observations (images + metadata + state)
- AI agent decides what to do next
- CLI executes deterministic control commands against the VNC session

## Scope guardrails (v1)
- Single VNC host only (no multi-host inventory/fleet management)
- Credentials come from CLI args or environment variables
- This tool is a bridge, not a full remote-desktop platform

## Planning docs
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [ROADMAP.md](./ROADMAP.md)
- [TASKS.md](./TASKS.md)

## Status
Groundwork complete. Moving into technical spike for library/runtime selection.
