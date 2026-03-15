# openclaw-vnc-control — Task Board

Status legend: `TODO` | `IN_PROGRESS` | `DONE` | `BLOCKED`

## Coordination
- Local workspace task id: `task-20260315-001` (tracked in `/tasks/ACTIVE.md`)

## Sprint A — Groundwork
- [DONE] Create project folder and public GitHub repo
- [DONE] Add initial README
- [DONE] Create architecture/roadmap/tasks planning docs
- [DONE] Lock scope: single-host bridge model + credentials via args/env
- [TODO] Add license file

## Sprint B — Technical Spike
- [DONE] Research landscape (ClawHub, Perplexity, X, GitHub) — no existing VNC bridge skill
- [DONE] Evaluate VNC libraries: vncdotool (Python/Twisted) selected
- [DONE] Proof of concept: connect + auth + screenshot working on macOS ARD
- [DONE] Proof of concept: pointer move + click working
- [DONE] Proof of concept: keyboard type + key working
- [DONE] End-to-end loop verified: screenshot → click → type → enter → screenshot
- [DONE] Benchmarked: ~1.5-2s per command (connect + action + disconnect)

## Sprint C — MVP CLI (current)
- [DONE] `vnc-control.py` CLI with all commands:
  - `status` — check host reachable (TCP probe + RFB banner)
  - `connect` — test full VNC auth + get screen dimensions
  - `screenshot` — capture screen to PNG (auto or explicit path)
  - `click` — click at x,y with button + double-click support + verify image
  - `move` — move pointer to x,y
  - `type` — type text string
  - `key` — send special keys (enter, tab, ctrl-c, etc.)
- [DONE] JSON output for all commands
- [DONE] Image metadata in output (path, size, width, height)
- [DONE] Env var + CLI arg credential model working
- [DONE] setup.sh + requirements.txt
- [DONE] macOS ARD flush workaround (key/move commands)
- [TODO] Add `disconnect` command (currently each cmd is a separate connection)
- [TODO] Persistent session mode (connect once, run multiple commands)
- [TODO] Add `drag` command
- [TODO] Add `--crop` support for regional screenshots

## Sprint D — Integration Testing
- [TODO] Automated end-to-end smoke test script
- [TODO] CI workflow

## Sprint E — API Wrapper
- [TODO] Local API interface with session routing
- [TODO] Mirror CLI commands in API

## Known Issues
- `key escape` times out on macOS ARD (other keys work)
- Each command opens/closes a VNC connection (latency overhead)
- 3420x2214 screenshots are ~10MB PNGs (may want JPEG option or downscale)

## Immediate Next Actions
1. Test against a non-macOS VNC server for compatibility
2. Add persistent session mode to reduce per-command latency
3. Add screenshot format options (JPEG, downscale)
