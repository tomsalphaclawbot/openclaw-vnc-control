# openclaw-vnc-control — Task Board

Status legend: `TODO` | `IN_PROGRESS` | `DONE` | `BLOCKED`

## Sprint A — Groundwork
- [DONE] Create project folder and public GitHub repo
- [DONE] Add initial README
- [DONE] Create architecture/roadmap/tasks planning docs
- [TODO] Add contribution and license files

## Sprint B — Technical Spike (48h)
- [TODO] Evaluate candidate VNC libraries (3 max)
- [TODO] Build minimal proof of connect + screenshot for top candidate
- [TODO] Capture benchmark notes (latency, stability, maintenance health)
- [TODO] Pick one library and record decision

## Sprint C — MVP Implementation
- [TODO] Implement session connect/disconnect/status
- [TODO] Implement screenshot command
- [TODO] Implement pointer move command
- [TODO] Implement click command
- [TODO] Add structured JSON response envelopes
- [TODO] Add timeout/retry defaults

## Sprint D — Integration Testing
- [TODO] Add local disposable VNC target for tests
- [TODO] Add automated end-to-end smoke test:
  - connect
  - screenshot
  - move/click
  - disconnect
- [TODO] Add CI workflow for smoke tests

## Sprint E — API Wrapper
- [TODO] Build local API interface with session routing
- [TODO] Mirror CLI commands in API
- [TODO] Add API examples and docs

## Risks / Watchlist
- VNC library maturity/maintenance risk
- Encoding compatibility across servers
- Cursor state drift under lag
- Reconnect semantics after transient disconnect

## Immediate Next Actions
1. Decide runtime/language.
2. Run technical spike and choose VNC library.
3. Build first working `connect + screenshot` command.
