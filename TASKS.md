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

## Sprint I — Vision Backend Benchmark Suite 🟡 NEXT

**Goal:** Systematic, reproducible comparison of all detection backends against the Click Lab. Before open-sourcing, anyone choosing a backend should have real data, not anecdotes.

**Test fixture:** `labs/vnc-click-lab/` — 22 named buttons in a 6×4 grid, known `xPct`/`yPct` ground-truth positions, existing log API. Already proven 22/22 by human-clicking. Now run all backends against it.

### Subtasks

#### I-1: Click Lab — start + health check script
- [ ] Script `bench/start_click_lab.sh` — launch `npm run dev` in lab dir, wait for port 3000 ready, open in browser via `open` command
- [ ] Verify lab is visible and navigable from a VNC screenshot
- [ ] Document how to position/size the browser window deterministically for consistent coordinates

#### I-2: Ground truth fixture
- [ ] Script `bench/ground_truth.py` — fetches button positions from the running lab page (parse `xPct`/`yPct` from JS or a `/api/buttons` endpoint we add)
- [ ] Alternatively: hardcode the 22 button positions in a `bench/fixtures.json` from the known grid formula (`startX=40, endX=90, startY=22, endY=88, cols=6, rows=4`)
- [ ] Output: `{"btn-1": {"label": "ATLAS PLUM", "x_pct": 40.0, "y_pct": 22.0}, ...}`

#### I-3: Benchmark runner
- [ ] Script `bench/run_benchmark.py` — for each backend × each button:
  1. Take screenshot of the lab
  2. Call `detect_element(image, f'button labeled {label}', backend=backend)`
  3. Compare detected center (normalized) vs ground truth (xPct/yPct)
  4. Record: found (bool), error_px, error_pct, elapsed_s, confidence
- [ ] Backends to test: `moondream`, `gemma4`, `anthropic`
- [ ] Output: `bench/results/YYYY-MM-DD-HH-MM-{backend}.json`

#### I-4: Metrics + report
- [ ] Script `bench/report.py` — reads results JSON(s), outputs:
  - Per-backend: accuracy (% found), median error_px, p95 error_px, median latency, total cost (for remote backends)
  - Per-button: which buttons each model struggled with (small text? similar colors? edge positions?)
  - Markdown table for README
- [ ] First-pass target: `moondream` and `anthropic` baselines (Gemma4 needs server running)

#### I-5: Extend Click Lab with more element types
- [ ] Add a text input field (test: "type in the search box")
- [ ] Add a dropdown / select element
- [ ] Add small icon buttons (stress test for small targets)
- [ ] Add two visually similar buttons with different labels (hardest case)
- [ ] Goal: test beyond rectangular colored buttons into realistic UI diversity

#### I-6: Integrate results into docs
- [ ] Add benchmark results table to `docs/vision-models.md`
- [ ] Update README with "Benchmark results" section linking to full data
- [ ] Add `bench/README.md` explaining how to reproduce

#### I-7: CI smoke (optional, if remote backend available)
- [ ] Add a lightweight single-button detection test to CI using a static screenshot fixture
- [ ] Tests the detection pipeline without needing live VNC or a running browser

### Definition of done
- All three backends benchmarked against all 22 buttons
- Metrics: accuracy %, median px error, p95 px error, median latency
- Results committed to `bench/results/`
- `docs/vision-models.md` updated with the data
- `bench/README.md` explains how to reproduce

---

## Sprint H — Vision-Assisted Coordinate Precision 🔴 HIGH PRIORITY

**Problem:** Click coordinates from LLM vision descriptions are approximate and unreliable. System dialogs re-trigger when clicks miss. Automated workflows (sudo prompts, permission dialogs, form fields) require pixel-accurate targeting.

**Goal:** replace "LLM guesses coordinates" with "local vision model detects bounding box, click the center."

### Subtasks
- [x] **Calibration audit** — synthetic marker round-trip audit implemented (`scripts/coord-calibration-audit.py`) with automated tests (`tests/test_coord_calibration_audit.py`) to measure screenshot→native precision objectively.
- [x] **Evaluate Moondream2** (`vikhyatk/moondream2`) — integrated as primary local backend with eval harness (`eval_moondream.py`) and documented in `docs/vision-models.md`.
- [ ] **Evaluate Florence-2** (Microsoft) — **de-scoped for this pass** pending local install + benchmark run; next command: `python3 eval_florence2.py --screenshot <path> --query "Allow button"` (scaffold/TODO tracked in docs).
- [ ] **Evaluate Meta SAM2** — still pending; likely only worth it if Moondream/Gemma miss-rate remains high after calibration.
- [x] **Build `click_element(description)` command** — shipped in v0.5.0 with local-first backends and Anthropic fallback.
- [x] **Click verification loop** — now computes post-click change metrics and supports offset retry (`--verify-retries`, `--retry-offset`) plus strict mode (`--require-state-change`).
- [x] **Calibration test suite** — synthetic screenshot benchmark path added via `scripts/coord-calibration-audit.py`.
- [x] **Update SKILL.md** with `click_element` and verification workflow notes.
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
