# openclaw-vnc-control — Roadmap

## Phase 0 — Foundations (current)
Goal: project skeleton, architecture, plan, and task breakdown.

Deliverables:
- [x] Public repository initialized
- [x] Planning docs (`ARCHITECTURE.md`, `ROADMAP.md`, `TASKS.md`)
- [ ] Decision on language/runtime
- [ ] Decision on VNC client library

## Phase 1 — Control Primitives MVP
Goal: reliable core operations from CLI.

Deliverables:
- [ ] Connect/auth to VNC host
- [ ] Capture screenshot
- [ ] Move pointer
- [ ] Click (single/double)
- [ ] Structured JSON output for all commands
- [ ] Basic reconnect + timeout handling

Exit criteria:
- Can connect to a real VNC host and perform screenshot + click end-to-end.

## Phase 2 — Programmatic API
Goal: expose primitives for agent/runtime integration.

Deliverables:
- [ ] Local API service wrapper
- [ ] Session creation + routing
- [ ] Command parity with CLI
- [ ] Auth/token model for local callers (minimal)

Exit criteria:
- External process can control VNC using API with deterministic responses.

## Phase 3 — Reliability + Test Harness
Goal: make it hard to break and easy to validate.

Deliverables:
- [ ] Integration tests against disposable VNC target
- [ ] Retry/backoff policy hardening
- [ ] Better diagnostics and error taxonomy
- [ ] CI workflow for smoke/integration

Exit criteria:
- Repeatable CI pass on core flows.

## Phase 4 — Developer Experience
Goal: easy adoption by other operators/builders.

Deliverables:
- [ ] Quickstart docs (<10 min)
- [ ] Example scripts
- [ ] Versioned release process
- [ ] Tagged v0.1.0 release
