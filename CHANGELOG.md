# Changelog

All notable changes to openclaw-vnc-control. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- `DESIGN.md` — open-source architecture and permission model spec
- Permission manifest concept (`vnc-permissions.json`) for multi-agent deployments
- Audit log design for per-action accountability

### Changed
- `cmd_wait_for` and `cmd_assert_visible` migrated to unified `detect_element()` layer
- Removed dead code: `_vision_find_element`, `_gemma4_detect`, `_moondream_detect` (replaced by unified layer)
- Removed hardcoded venv path from Moondream backend

---

## [0.5.0] — Sprint H: Vision-Assisted Coordinate Precision (2026-04-04)

### Added
- **Unified detection layer** — `detect_element(image_path, query, backend)` single entry point for all vision backends
- **Canonical `DetectionResult` schema** — all backends return identical structure: `box`, `box_norm`, `center`, `center_norm`, `capture_scale`, `native_coords`
- **`click_element` command** — natural language element targeting, no hardcoded coords
- **`--backend` flag** — choose `moondream` (local MPS), `gemma4` (local server), or `anthropic` (remote API) per call
- **Moondream2 backend** (`vikhyatk/moondream2`) — local MPS inference, ~5-8s, no API cost
- **Gemma4 backend** — calls local OpenAI-compatible server at port 8890, ~5-8s
- **Coord translation fix** — `cmd_click_element` now uses `resolve_native_coords()` + `capture_settings()` instead of hardcoded `SCALE=0.5`
- `docs/vision-models.md` — per-model latency, accuracy, trade-off reference

### Fixed
- `result_json()` `method` NameError in `cmd_click_element` output
- `cmd_wait_for` and `cmd_assert_visible` now use canonical detection schema

---

## [0.4.0] — Sprint G: Workflow Engine + Vision (2026-03-20 → 2026-04-03)

### Added
- **Phase 17** — Workflow event hooks (`step_start`, `step_end`, `step_fail`, `workflow_complete`)
- **Phase 16** — Conditional step execution (`when` expressions in workflow YAML)
- **Phase 15** — YAML/JSON workflow runner with interpolation, retry, dry-run (42 unit tests)
- **Phase 14** — `read_text` OCR extraction (screen/file, region crop, `--raw` mode)
- **Phase 13** — Clipboard integration (`get`/`set`/`copy`/`paste`)
- **Phase 12** — Macro record/play/list
- **Phase 11** — Screenshot annotation (rect/circle/arrow/text, named colors)
- **Phase 10** — Region-of-Interest crop with coverage_pct
- **Phase 9** — Image diff / change detection with bounding box overlay
- **Phase 8** — Scroll and drag gestures
- **Phase 7** — Vision-assisted automation: `find_element`, `wait_for`, `assert_visible`
- Multi-backend vision model support (configurable via `VNC_VISION_MODEL` env)

---

## [0.3.0] — Sprint F: Sessions + API (2026-03-17 → 2026-03-19)

### Added
- **Phase 6** — Multi-session support (`sessions.json`, `--session` flag, `/sessions/*` API routes)
- **Phase 5** — HTTP API wrapper (FastAPI server, 13 unit tests)
- CI: skip OCR tests when `tesseract` binary missing

### Fixed
- pytest-timeout and pyyaml added to requirements for CI

---

## [0.2.0] — Sprint D–E: Daemon + Click Lab (2026-03-15 → 2026-03-16)

### Added
- **v2 Session daemon** — persistent VNC socket, `vnc` subcommands
- **Click Lab** (`labs/vnc-click-lab/`) — standalone Next.js accuracy test app, 22-button grid
- **Sprint D** — `detect_lock_screen()` PIL heuristic, `unlock()` retry macro, unit tests (39/39 green)
- **Sprint F completion** — pytest smoke suite (8 tests), SKILL.md v2 rewrite, `.env.example`, MIT LICENSE
- `normalize_key_name()` — fixes `Return` → `enter` macOS ARD case-sensitivity bug
- Coordinate system: screenshot / native / normalized spaces with auto-conversion
- `map` command — coordinate space conversion
- JPEG output + scale flag for AI-friendly screenshots
- SHA1 change detection, process group kill preventing zombies

### Fixed
- `Return` key timeout on macOS ARD (alias to `enter`)
- Lock screen password entry via daemon (partial — raw vncdo workaround)

---

## [0.1.0] — Sprint A–C: Core VNC Bridge (2026-03-14 → 2026-03-15)

### Added
- Initial scaffold: architecture doc, roadmap, task plan
- Core CLI: `screenshot`, `click`, `type`, `key`, `move`
- AgentSkill (`SKILL.md`) for AI-driven VNC control loops
- JPEG capture with configurable scale (AI efficiency profile)
- macOS Screen Sharing support (vs Remote Management — see Known Issues)
- `v1` AI profile mode — efficiency-first defaults
- Automated click regression scripts
- VNC click lab assets integrated

### Architecture
- CLI-first, JSON stdout, subprocess-friendly
- Objective preflight required before every command (SKILL.md requirement)
- Credentials via env vars (`VNC_HOST`, `VNC_PORT`, `VNC_USERNAME`, `VNC_PASSWORD`)
- Platform: macOS ARD / Screen Sharing, vncdotool 1.2.0

---

## Platform Notes

**macOS ARD quirks documented across sprints:**
- `Return` (capitalized) always times out — use `enter` (lowercase)
- TCC dialogs ignore VNC mouse events — use AppleScript accessibility layer
- Screen Sharing works reliably; Remote Management causes auth-mode confusion
- `iogpu.wired_limit_mb` sysctl needed when running alongside Docker to prevent OOM swap storms

---

[Unreleased]: https://github.com/tomsalphaclawbot/openclaw-vnc-control/compare/main...HEAD
[0.5.0]: https://github.com/tomsalphaclawbot/openclaw-vnc-control/compare/v0.4.0...main
[0.4.0]: https://github.com/tomsalphaclawbot/openclaw-vnc-control/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/tomsalphaclawbot/openclaw-vnc-control/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/tomsalphaclawbot/openclaw-vnc-control/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/tomsalphaclawbot/openclaw-vnc-control/releases/tag/v0.1.0
