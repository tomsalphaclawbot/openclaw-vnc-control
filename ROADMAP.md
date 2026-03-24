# openclaw-vnc-control — Roadmap

## Phase 0 — Foundations ✅
- [x] Public repo: https://github.com/tomsalphaclawbot/openclaw-vnc-control
- [x] Architecture + planning docs
- [x] Pick runtime: Python 3
- [x] Pick VNC library: vncdotool (subprocess)
- [x] Lock scope: single-host bridge, CLI-first

## Phase 1 — Visual Bridge MVP ✅
- [x] Connect/auth to VNC host (standard + macOS ARD)
- [x] Capture screenshot → PNG
- [x] JPEG output + scaling (50% default, ~350KB)
- [x] Move pointer to x,y
- [x] Click at x,y (single/double, left/right/middle)
- [x] Type text / send keystrokes
- [x] Key combos (ctrl-c, shift-1, super_l-a, etc.)
- [x] JSON output for all commands
- [x] macOS ARD quirk workarounds documented and implemented
- [x] End-to-end loop verified (screenshot → click → type → screenshot)
- [x] setup.sh + requirements.txt

## Phase 2 — Session Daemon (v2) ✅
- [x] Daemon architecture: Unix socket server, vncdo subprocess dispatch
- [x] `vnc` wrapper script (PATH-accessible, resolves symlinks)
- [x] Keepalive: 25s center-area mouse jiggle (avoids hot corners)
- [x] Coordinate spaces: native / capture / normalized with auto-conversion
- [x] Screenshot via daemon working (JPEG 50%, ~350KB, ~0.6s)
- [x] Click, move, type, key via daemon working
- [x] Lock screen detection from screenshot analysis (`detect_lock_screen` command)
- [x] Auto-unlock macro with retry logic (`unlock` command)
- [x] **Note:** `key return` intermittent on macOS ARD — documented quirk, unlock uses workaround

## Phase 3 — Agent Skill Package ✅
- [x] `skill/SKILL.md` — AgentSkill spec with frontmatter
- [x] `skill/scripts/install.sh` — one-command setup
- [x] `skill/scripts/agent-loop-example.sh` — demo loop
- [x] Self-installed as OpenClaw native skill (symlinked)
- [x] TOOLS.md updated (references .env, not plaintext creds)

## Phase 4 — Hardening ✅ (completed 2026-03-24)
- [x] Automated test suite: 31 unit tests + 8 integration tests (VNC-skip-safe) — 39/39 green
- [x] `pytest.ini` wired; `tests/test_unit.py` + `tests/test_integration.py`
- [x] `.env.example` template
- [x] License file (MIT)
- [x] CI workflow — `.github/workflows/ci.yml`: unit tests on every push/PR (2026-03-24, fixed 2026-03-24)
- [x] Tagged v0.1.0 release (2026-03-24)
- [x] Deferred: test against non-macOS VNC target (no external target available; documented limitation)

## Phase 5 — HTTP API Wrapper ✅ COMPLETE 2026-03-24
Target: make the VNC bridge consumable via HTTP for multi-agent and remote orchestration.
- [x] `vnc_api.py` — FastAPI server wrapping all CLI commands (shim: `vnc-api.py`)
- [x] Auth: shared secret header via `X-VNC-API-Secret` (env: `VNC_API_SECRET`)
- [x] Endpoints: `GET /status`, `POST /screenshot`, `POST /click`, `POST /move`, `POST /type`, `POST /key`
- [x] Return screenshot as base64 in JSON response (no filesystem dep for callers)
- [x] `--port` and `--bind` args; defaults: 127.0.0.1:7472
- [x] Unit tests for API routes — 13/13 passing (`tests/test_vnc_api.py`)
- [x] Update skill/SKILL.md and README with API mode (2026-03-24)
- [x] Tagged v0.2.0 release (2026-03-24)

## Phase 6 — Multi-Session Support ✅ DONE (v0.3.0, 2026-03-24)
- [x] Session registry: name → (host, port, creds) — `sessions.json` + `sessions.json.example`
- [x] `sessions.json` config file with `default` key support
- [x] `--session <name>` / `-S <name>` flag on all commands (global parser flag)
- [x] Graceful fallback to env-var defaults when no session specified
- [x] `sessions list` / `sessions show <name>` subcommand (password redacted)
- [x] HTTP API session-scoped routes: `GET /sessions`, `GET /sessions/{name}`, `/sessions/{name}/status|screenshot|click|type|key`
- [x] 15 unit tests — 15/15 passing (total suite: 67/67)

## Phase 7 — Vision-Assisted Automation ✅ DONE 2026-03-24
- [x] `find_element <description>` — screenshot + Anthropic vision API → returns click coordinates (screenshot space + native_x/native_y)
- [x] `wait_for <description>` — screenshot loop until element appears or timeout; configurable --timeout/--interval
- [x] `assert_visible <description>` — verify UI state without hardcoded coords; exits 0=found, 1=not found
- [x] `_vision_find_element()` — shared vision core: base64 screenshot → Claude vision → parsed JSON response
- [x] Markdown fence stripping for model responses that wrap JSON in ```code``` blocks
- [x] 6 new unit tests (37/37 total passing); full suite 65/65 with no regressions
- [x] `VNC_VISION_MODEL` env var + `--model` per-command override (default: claude-opus-4-5)
- [x] `base64` and `urllib.request` moved to module-level imports (cleaner + testable)

## Phase 8 — Scroll & Drag ✅ DONE 2026-03-24
- [x] `scroll X Y <direction>` — mouse wheel scroll at position (button 4=up/right, button 5=down/left)
- [x] `--clicks N` for scroll intensity (1-50, default 3), clamped for safety
- [x] `drag X1 Y1 X2 Y2` — click-and-drag between two points using vncdo mousedown→drag→mouseup
- [x] `--button` option for drag (left/right/middle, default left)
- [x] Both commands support `--space`, `--native`, `--scale` (same as click/move)
- [x] Verify screenshot captured after both scroll and drag
- [x] 11 new unit tests: direction mapping, click clamping, coordinate resolution, CLI parser validation
- [x] Full suite: 81 passed, 5 skipped (up from 68+5)
- [x] Tagged v0.5.0

## Abandoned Approaches (documented for future reference)
- **vncdotool threaded API**: `captureScreen` hangs on macOS ARD (framebuffer timeout)
- **asyncvnc**: Screenshots all-black (encoding limitation)
- **vncdo stdin mode**: Can't interleave commands (batch-then-exit only)
- **Persistent connection pooling**: All tested persistent approaches fail on macOS ARD
