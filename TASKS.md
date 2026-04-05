# openclaw-vnc-control — Task Board

Status: `TODO` | `IN_PROGRESS` | `DONE` | `BLOCKED`

## Coordination
- Local workspace task id: `task-20260315-001` (tracked in `/tasks/ACTIVE.md`)

---

## Sprint A — Groundwork ✅ DONE
- [DONE] Create project folder and public GitHub repo
- [DONE] README, ARCHITECTURE, ROADMAP, TASKS docs
- [DONE] Lock scope: single-host bridge, args/env credentials, CLI-first
- [DONE] Add license file (MIT, 2026-03-18)
- [DONE] Add `.env.example` template (2026-03-18)

## Sprint B — Technical Spike ✅ DONE
- [DONE] Research landscape: ClawHub (computer-use, virtual-remote-desktop, remote-desktop), Perplexity, X, GitHub
- [DONE] Gap confirmed: no existing VNC bridge skill for AI agent loops
- [DONE] Evaluated libraries:
  - vncdotool (Python/Twisted) — **selected**: reliable via subprocess, macOS ARD auth works
  - asyncvnc — tested, screenshots return all-black (encoding limitation)
  - vncdotool threaded API — tested, captureScreen hangs on macOS ARD
  - vncdo stdin mode — tested, batch-then-exit only (can't interleave)
- [DONE] Proof of concept: connect + auth + screenshot + click + type + key

## Sprint C — v1 Standalone CLI ✅ DONE
- [DONE] `vnc-control.py` with all commands: status, connect, screenshot, click, move, type, key
- [DONE] JSON output for all commands
- [DONE] JPEG output + --format/--scale/--quality
- [DONE] Image size optimization: PNG 10MB → JPEG 50% ~350KB (sufficient for AI vision)
- [DONE] Env var + CLI arg credential model
- [DONE] setup.sh + requirements.txt
- [DONE] macOS ARD flush workaround (key/move append throwaway capture)
- [DONE] `key escape` timeout documented

## Sprint D — v2 Session Daemon 🔧 IN PROGRESS
- [DONE] `vnc-session.py` daemon: Unix socket server, PID file, signal handling
- [DONE] Dispatch via vncdo subprocess (proven reliable, ~0.6-1.3s per command)
- [DONE] `vnc` shell wrapper: resolves symlinks, activates venv, PATH-accessible via ~/.local/bin
- [DONE] Keepalive: 25s center-area mouse jiggle
  - **BUG FOUND+FIXED**: keepalive was jiggling to (1,1) which hit macOS top-left hot corner (set to "Put Display to Sleep"). Fixed: disabled hot corner + moved jiggle to center.
- [DONE] Coordinate spaces: native / capture / normalized with auto-conversion
- [DONE] All commands working through daemon: ss, click, move, type, key, status, stop
- [IN_PROGRESS] Lock screen unlock reliability
  - Password typing works (14 dots confirmed for 14-char password)
  - `key return` submit intermittently fails/hangs
  - `--force-caps` mode vs manual `key shift-1` for `!` character
  - Click on submit arrow button — coordinates need refinement
  - **Root cause hypothesis**: macOS ARD lock→desktop transition doesn't produce expected VNC framebuffer response, causing vncdo to block
- [DONE] Lock detection from screenshot signature (`detect_lock_screen`: luminance + center-card + arrow-button heuristics; unit-tested 2026-03-18)
- [DONE] Auto-unlock macro with retry logic (`unlock`: click field → clear → paste pw → click arrow / fallback key return → verify with detect_lock_screen; up to N retries; 2026-03-18)
- [DONE] macOS lock behavior tuned for VNC stability
  - `defaults -currentHost write com.apple.screensaver idleTime -int 1800`
  - `defaults write com.apple.screensaver askForPasswordDelay -int 1800`
  - Battery `displaysleep 2` still needs sudo to change; AC `displaysleep 0` is already correct
  - Hot corners all disabled (tl=1, bl=1, br=1)
  - Tom-confirmed root cause: Lock Screen policy was set to **"Require password ... After 2 seconds"**, causing fast relock when display sleep/screensaver triggered during VNC disconnects/transitions
  - Tom changed this policy to **1 hour** in System Settings (verified)
  - Node TCC permissions dialog dismissed via VNC click

## Sprint E — Skill Package ✅ DONE
- [DONE] `skill/SKILL.md` — OpenClaw AgentSkill format with YAML frontmatter
- [DONE] `skill/scripts/install.sh` — one-command setup
- [DONE] `skill/scripts/agent-loop-example.sh` — demo agent loop
- [DONE] Symlinked into workspace skills dir
- [DONE] TOOLS.md credential security fix (removed plaintext, reference .env/Bitwarden)

## Sprint F — Hardening ✅ DONE
- [DONE] Automated e2e smoke test — tests/test_unit.py (31 tests) + tests/test_integration.py (8 tests, VNC-skip-safe); pytest.ini wired; 39/39 green (2026-03-18)
- [DEFERRED] Test against non-macOS VNC target — no external target available; documented as limitation
- [DONE] CI workflow — .github/workflows/ci.yml: unit tests on every push/PR; integration tests gated on VNC_HOST secret (2026-03-24)
- [DONE] Tagged v0.1.0 release (2026-03-24)

---

## Known Issues

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | `key escape` times out on macOS ARD | Low | Documented, workaround in place |
| 2 | macOS auto-locks in ~1-2 min | High | **FIXED** — root cause was Lock Screen "Require password" set to 2s; changed to 1h + screensaver/pmset tuning |
| 3 | `key return` unreliable for lock screen submit | High | IN_PROGRESS |
| 4 | `!` char in `type` may encode wrong | Medium | Use `--force-caps` or `key shift-1` |
| 5 | Daemon keepalive hit hot corner causing lock | Critical | **FIXED** — center jiggle + hot corner disabled |
| 6 | Persistent API connections all fail on macOS ARD | Info | Abandoned, using subprocess |

## Research Log

### VNC Libraries Tested
| Library | Connects? | Screenshot? | Input? | Verdict |
|---------|-----------|-------------|--------|---------|
| vncdotool (subprocess) | ✅ | ✅ (~1.3s) | ✅ | **Selected** |
| vncdotool (threaded API) | ✅ | ❌ timeout | ✅ | Abandoned |
| asyncvnc | ✅ | ❌ all-black | ✅ | Abandoned |
| vncdo stdin | ✅ | ✅ | ✅ | Batch-only, not interactive |

### Competitive Landscape (searched 2026-03-15)
- **ClawHub "computer-use"**: Xvfb + xdotool, not VNC protocol
- **ClawHub "virtual-remote-desktop"**: KasmVNC, not generic VNC bridge
- **ClawHub "remote-desktop"**: Connection/tunneling guide, not agent loop
- **mcp-vnc** (GitHub): MCP server for Claude Desktop. Closest match but MCP-only, no CLI
- **vncdotool**: Mature CLI/lib but no structured output, not agent-oriented
- **Result**: No existing tool provides standalone VNC bridge for AI agent loops. Gap confirmed.

## Sprint I — Vision Backend Benchmark Suite ✅ PARTIAL COMPLETE (2026-04-05)

**Goal:** Systematic, reproducible comparison of all detection backends against the Click Lab. Before open-sourcing, backend selection should be driven by measured data.

**Measured run:** `bench/results/matrix-20260405/`
- Fixture: `fixture.json` + `fixture-click-lab.png`
- Matrix artifacts: `benchmark_matrix.json`, `benchmark_matrix.csv`, `benchmark_matrix.md`
- Cases: 10 total (8 positive + 2 negative)

### Subtasks

#### I-1: Click Lab — start + health check script
- [x] Script `bench/start_click_lab.sh` (port-aware launcher, health wait, PID/log output)
- [x] Verified fixture app at `http://127.0.0.1:3015/vnc-click-lab`
- [x] Deterministic viewport in fixture capture (`1710x913`) via Playwright screenshot flow

#### I-2: Ground truth fixture
- [x] Script `bench/capture_fixture.py` captures screenshot + pulls `/api/element-coords` snapshot
- [x] Output includes per-element center px + normalized center + metadata
- [x] Fixture committed at `bench/results/matrix-20260405/fixture.json`

#### I-3: Benchmark runner
- [x] Script `bench/run_benchmark_matrix.py` executes backend × case matrix against fixture
- [x] Backends in matrix: `moondream`, `gemma4`, `anthropic`, `falcon`, `florence2`, `sam2`
- [x] Runnable in this environment: `moondream`, `gemma4`
- [x] Non-runnable backends are recorded with `reason_class`, concrete `reason`, dry-run command, and next steps

#### I-4: Metrics + report
- [x] Per-backend metrics emitted: positive recall, negative specificity, median/p95 px error, median latency
- [x] Machine-readable + human-readable outputs emitted (`json`, `csv`, `md`)
- [x] First-pass measured ranking documented in `docs/vision-models.md`

#### I-5: Extend Click Lab with more element types
- [ ] Existing lab already includes forms/icons/modals/dynamic pages; matrix currently run on `/vnc-click-lab` fixture only
- [ ] Follow-up: add fixture captures for forms/icons/modals and rerun matrix across those pages

#### I-6: Integrate results into docs
- [x] Added benchmark table + recommendation ordering to `docs/vision-models.md`
- [x] Added `bench/README.md` reproducibility runbook
- [x] Added README benchmark section linking artifacts

#### I-7: CI smoke (optional, if remote backend available)
- [x] Added unit tests for matrix harness logic: `tests/test_benchmark_matrix.py`
- [ ] Optional: wire static fixture smoke into CI pipeline

### Definition of done (current state)
- [x] Reproducible harness + fixture pipeline implemented
- [x] Runnable backends benchmarked with structured artifacts
- [x] Docs updated with measured data and backend ordering
- [ ] Full cross-page fixture matrix (forms/icons/modals/density/dynamic)
- [ ] Anthropic/falcon/florence measured rows once credentials/models are available

---

## Sprint H — Vision-Assisted Coordinate Precision 🔴 HIGH PRIORITY

**Problem:** Click coordinates from LLM vision descriptions are approximate and unreliable. System dialogs re-trigger when clicks miss. Automated workflows (sudo prompts, permission dialogs, form fields) require pixel-accurate targeting.

**Goal:** replace "LLM guesses coordinates" with "local vision model detects bounding box, click the center."

### Subtasks
- [ ] **Calibration audit** — verify screenshot-space → native-space coordinate math end-to-end with a synthetic marker test (draw pixel at exact known coord, screenshot, verify round-trip accuracy)
- [ ] **Evaluate Moondream2** (`vikhyatk/moondream2`) — compact 1.86B vision model, MLX port available, strong UI element grounding. Test: screenshot + "click the Allow button" → bounding box accuracy.
- [ ] **Evaluate Florence-2** (Microsoft) — strong at grounding/detection, small footprint (~0.2B), CoreML compatible. Compare to Moondream2 on button detection accuracy.
- [ ] **Evaluate Meta SAM2** — segment-anything-2 for click-point generation. Likely overkill but test if accuracy warrants the RAM cost.
- [ ] **Build `click_element(description)` command** — natural language → local vision model → precise center coords → click. Fallback to remote API vision if local model unavailable.
- [ ] **Click verification loop** — post-click screenshot diff to confirm state change (dialog dismissed, etc.). Retry with offset correction if unchanged.
- [ ] **Calibration test suite** — synthetic screenshots with buttons at known positions, measure model detection error distribution.
- [ ] **Update SKILL.md** with new `click_element` command and local-model setup instructions.
- [ ] Tag v0.5.0 on completion.

### Decision criteria
- Must run locally (no per-click API latency)
- Apple Silicon / MLX preferred
- Target: button center within 5px
- Vision model RAM footprint: ≤4GB

---

## Immediate Next Actions
1. ~~Fix lock screen unlock reliability (Issue #3)~~ ✅ detect_lock_screen + unlock with retry (2026-03-18)
2. ~~Create `.env.example` template~~ ✅ done 2026-03-18
3. ~~Add license file~~ ✅ MIT license added 2026-03-18
4. ~~Update skill/SKILL.md for v2 daemon usage (detect-lock / unlock commands)~~ ✅ done 2026-03-18
5. Commit all v2 changes and push ← next
6. Live test detect-lock + unlock against a locked macOS ARD session
7. Sprint F: automated e2e smoke test, tagged v0.1.0 release

## Sprint G — Phase 7 Vision-Assisted Automation ✅ DONE 2026-03-24
- [DONE] `_vision_find_element()`: screenshot → Anthropic vision API → parsed coordinates
- [DONE] `find_element <description>`: locate UI element by natural language, return x/y in screenshot space + native coords
- [DONE] `wait_for <description>`: poll loop with --timeout (default 30s) + --interval (default 2s) until element found or timeout
- [DONE] `assert_visible <description>`: single-shot assertion, exit 0=found / 1=not found
- [DONE] Markdown fence stripping (models wrap JSON in ```code blocks```)
- [DONE] --model flag + VNC_VISION_MODEL env override; default model: claude-opus-4-5
- [DONE] 6 new unit tests; 37/37 unit, 65/65 total — no regressions
- [DONE] Tagged v0.4.0
