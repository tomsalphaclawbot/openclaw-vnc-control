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

## Phase 6 — Multi-Session Support (future)
- [ ] Session registry: name → (host, port, creds)
- [ ] `sessions.json` config file
- [ ] `--session <name>` flag on all commands
- [ ] Graceful fallback to env-var defaults when no session specified
- [ ] Daemon multi-target: route commands to correct connection

## Phase 7 — Vision-Assisted Automation (future)
- [ ] `find_element <description>` — screenshot + OCR/vision model → returns click coordinates
- [ ] `wait_for <condition>` — screenshot loop until element/text appears or timeout
- [ ] `assert_visible <text>` — verify UI state without hardcoded coords
- [ ] Integration with OpenClaw image tool as the vision backend

## Abandoned Approaches (documented for future reference)
- **vncdotool threaded API**: `captureScreen` hangs on macOS ARD (framebuffer timeout)
- **asyncvnc**: Screenshots all-black (encoding limitation)
- **vncdo stdin mode**: Can't interleave commands (batch-then-exit only)
- **Persistent connection pooling**: All tested persistent approaches fail on macOS ARD
