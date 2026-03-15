# openclaw-vnc-control — Roadmap

## Phase 0 — Foundations (current)
- [x] Public repo
- [x] Architecture + planning docs
- [ ] Pick language/runtime
- [ ] Pick VNC client library

## Phase 1 — Visual Bridge MVP
Get the screenshot→click→screenshot loop working end-to-end.

- [ ] Connect/auth to VNC host
- [ ] Capture screenshot → image file
- [ ] Move pointer to x,y
- [ ] Click at x,y (single/double, left/right)
- [ ] Type text / send keystrokes
- [ ] Basic timeout + error handling

**Done when:** can connect to a real VNC host, screenshot, click somewhere, screenshot again.

## Phase 2 — Agent Integration
Make it easy for AI agents to use.

- [ ] Local API wrapper (optional)
- [ ] Example integration with OpenClaw image analysis
- [ ] Session management for long-running control loops

## Phase 3 — Hardening
- [ ] Integration tests against disposable VNC target
- [ ] CI workflow
- [ ] Retry/reconnect policies
- [ ] Tagged v0.1.0 release + quickstart docs
