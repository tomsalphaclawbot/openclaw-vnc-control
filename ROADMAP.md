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

## Phase 9 — Image Diffing / Change Detection ✅ DONE 2026-03-24
- [x] `diff <before> <after>` — compare two screenshots pixel-by-pixel
- [x] `--threshold N` — configurable change sensitivity (default: 10/255)
- [x] Returns: `changed`, `change_pct`, `changed_pixels`, `total_pixels`, `bounding_box`, `mean_diff_per_channel`
- [x] Bounding box covers minimal rectangle enclosing all changed pixels (x, y, x2, y2, width, height)
- [x] Annotated overlay image: after-image with red highlights on changed regions + orange bbox rectangle
- [x] Auto-resize if before/after differ in dimensions (handles screenshot scale changes)
- [x] 6 unit tests (56/56 total passing + 5 skipped integration)
- [x] Tagged v0.6.0

## Phase 10 — Region-of-Interest Crop ✅ DONE 2026-03-25
- [x] `crop <source>` — extract sub-region from screenshot or image file
- [x] `--region X Y W H` in screenshot/native/normalized coordinate spaces (auto-detected from args)
- [x] `--space screenshot|native|normalized` — explicit space override
- [x] Auto-clamp region to image bounds (never out-of-range error)
- [x] `coverage_pct` in output — fraction of original image area covered
- [x] `--out` for saving cropped image; `--format`/`--quality` options
- [x] 7 unit tests (63/63 total passing with no regressions)
- [x] Tagged v0.7.0
- **Rationale:** Enables focused analysis on sub-regions without passing the full screenshot to vision API. Reduces cost and improves accuracy for dense UIs.

## Phase 11 — Screenshot Annotation ✅ DONE 2026-03-25
- [x] `annotate <source> --shape SPEC [--shape SPEC ...]` — draw labeled shapes on screenshots
- [x] Shape types: `rect` (outlined + semi-transparent fill), `circle`, `arrow` (with arrowhead), `text` (with background box)
- [x] 10 named colors (red/green/blue/yellow/orange/purple/cyan/pink/white/black) + hex (#RRGGBB)
- [x] Optional labels drawn adjacent to each shape
- [x] `--line-width` control (default 2px)
- [x] `--format` (jpeg/png), `--quality`, `--out` options
- [x] Graceful handling of malformed shape specs (error entry in output, no crash)
- [x] 11 unit tests (110/110 total passing + 0 regressions)
- [x] Tagged v0.8.0
- **Rationale:** Close the agent feedback loop — after vision API locates an element, annotate the screenshot with bounding boxes/arrows for visual confirmation before clicking.

## Phase 12 — Macro Record & Playback ✅ DONE 2026-03-25
- [x] `macro record <file>` — read JSON action list from stdin → save as named macro file
- [x] `macro play <file>` — replay recorded actions with configurable `--delay-scale` (0=no delays, 1=real-time, 2=double)
- [x] `macro list <file>` — inspect macro action count + summary without executing
- [x] 7 action types supported: `click`, `move`, `type`, `key`, `scroll`, `drag`, `wait`
- [x] `--continue-on-error` flag: skip failed steps instead of aborting (default: abort on first failure)
- [x] `_resolve_coords` extracted helper shared across commands (screenshot/native/normalized → native)
- [x] Returns structured JSON: `total`, `executed`, `passed`, `failed`, `aborted_at_step`
- [x] 20 unit tests: resolve_coords (6), list (3), record (4), play (7) — total suite 130/130 passing
- [x] Tagged v0.9.0
- **Rationale:** Record-once-replay-many for repetitive GUI flows. Complements workflow runner (Phase 15) for raw action-level sequences vs. higher-level step abstractions.

## Phase 13 — Clipboard Integration ✅ DONE 2026-03-25
- [x] `clipboard get` — read current clipboard text via OS native tools (pbpaste on macOS, xclip on Linux)
- [x] `clipboard set --text TEXT` — write text to clipboard (pbcopy/xclip)
- [x] `clipboard copy` — send Cmd+C (macOS) / Ctrl+C (Linux) to focused element, return clipboard contents
- [x] `clipboard paste --text TEXT` — set clipboard to TEXT then send Cmd+V / Ctrl+V
- [x] `--delay SECS` option for copy (default: 0.3s after key send before reading)
- [x] Auto-detects macOS vs Linux (different key combos + clipboard tools)
- [x] Graceful error handling for missing clipboard tools (FileNotFoundError, timeout)
- [x] Returns structured JSON: `clipboard`, `length`, `lines`, `key_sent`, `key_duration_ms`
- [x] 10 unit tests (73/73 total passing + 0 regressions)
- [x] Tagged v0.9.1
- **Rationale:** Completes the read-back loop. Vision API extracts text from screenshots (slow + ~$0.01/call). Clipboard reads it for free. Workflow: `find_element` → `click` → `clipboard copy` → inspect text without another vision call.

## Phase 14 — OCR Text Extraction ✅ DONE 2026-03-25
- [x] `read_text` command — extract text from screen or image file using Tesseract OCR
- [x] `--source screen|file` — screenshot live screen or read from image path
- [x] `--region X Y W H` — optional crop before OCR (avoids full-screen noise)
- [x] `--lang LANG` — Tesseract language code (default: eng)
- [x] `--psm N` — Tesseract page segmentation mode (default: 3 = fully automatic)
- [x] `--raw` mode — per-word confidence scores + bounding boxes (via pytesseract image_to_data)
- [x] `--out FILE` — save intermediate cropped/processed image for debugging
- [x] Uses pytesseract (requires Tesseract 5.x binary; 5.5.2 installed locally)
- [x] 8 unit tests (81/81 total passing; OCR binary tests skip gracefully in CI)
- [x] Tagged v1.0.0 (first major version milestone)
- **Rationale:** Replaces vision-API-per-text-element with local OCR for high-frequency text reads. Orders of magnitude cheaper than Claude vision for simple label/number extraction.

## Phase 15 — Workflow Runner ✅ DONE 2026-03-25
- [x] `vnc-workflow.py` — YAML/JSON workflow engine; chains vnc-control commands into reusable automation scripts
- [x] `vnc_workflow.py` — importable module alias for testing
- [x] Step execution with retry logic (`retry_max`, `retry_delay`), `on_error: stop|continue|retry`
- [x] Variable interpolation: `{{var_name}}`, `{{step_id.field}}`, `{{step_id.data.field}}` — cascading var lookup
- [x] `save_output` — capture step result into named variable for downstream steps
- [x] Dry-run mode (`--dry-run`) — validates + shows plan without executing
- [x] Built-in commands: `sleep`, `echo` (no VNC required)
- [x] `vnc-workflow validate FILE` — standalone validation without execution
- [x] `vnc-workflow list` — discover workflow files in `workflows/` dir
- [x] `--var KEY=VALUE` CLI overrides for workflow variables
- [x] `--example` flag: run built-in demo workflow without a file path
- [x] 42 unit tests (159/159 total suite passing, 4 skipped)
- [x] Sample workflows: `workflows/screenshot-and-check.json`, `workflows/find-and-click.json`
- [x] Tagged v1.1.0
- **Rationale:** Enables agents to write automation workflows once and replay deterministically. Eliminates per-step round-trips. Foundation for multi-step GUI automation (login flows, dialog handling, form filling).

## Phase 16 — Conditional Workflow Execution ✅ DONE 2026-03-25
- [x] `when` field on workflow steps — skip steps based on runtime conditions
- [x] Literal shortcuts: `when: "true"` (always run) / `when: "false"` (always skip)
- [x] String equality/inequality: `"{{step.field}} == value"` / `"{{step.field}} != value"`
- [x] Numeric comparisons: `>`, `>=`, `<`, `<=` — both LHS and RHS interpolated before comparison
- [x] Boolean checks: `"{{step.ok}} == true"` / `"{{step.ok}} != false"`
- [x] Conditional-skipped steps tracked separately (`steps_conditional_skipped` counter)
- [x] Skipped step outputs registered for downstream reference (downstream steps can still reference them)
- [x] 31 new unit tests (186/186 total passing, 5 skipped)
- [x] Sample workflow: `workflows/conditional-check.yaml`
- [x] Tagged v1.2.0
- **Rationale:** Enables branching automation logic. Example: only click "Save" if a previous `find_element` step succeeded; only retry unlock if `detect_lock_screen` returned true.

## Phase 17 — Workflow Event Hooks ✅ DONE 2026-03-25
- [x] `step_start` hook — shell command fired before each step runs
- [x] `step_end` hook — fires after each step (pass or fail); receives step result as env vars
- [x] `workflow_complete` hook — fires at workflow end; `WORKFLOW_SUMMARY_JSON` env var contains full result JSON
- [x] `step_fail` hook — fires only when a step fails (after `step_end`)
- [x] Hook commands run via subprocess with 30s timeout; non-zero exit does NOT abort workflow by default
- [x] Configurable `hook_on_error: stop|ignore` (workflow-level setting)
- [x] Environment variables injected: `STEP_ID`, `STEP_OK`, `STEP_DURATION_MS`, `STEP_COMMAND`, `STEP_ATTEMPTS`, `WORKFLOW_NAME`
- [x] Workflow-level `hooks` block with `step_start`, `step_end`, `workflow_complete`, `step_fail` keys
- [x] Per-step `hooks` block overrides global hooks for that step only (empty string disables)
- [x] `{{VAR}}` interpolation supported in hook command strings
- [x] Hook results attached to step records under `hooks` key; workflow_complete under `workflow_complete_hook`
- [x] Hooks do NOT fire for conditionally-skipped steps (Phase 16 `when: false`)
- [x] `fire_hook()` function + `_resolve_step_hooks()` merge helper
- [x] 24 unit tests (176/176 total suite passing, 5 skipped)
- [x] Sample workflow: `workflows/hooked-workflow.yaml`
- [x] CI updated to include `tests/test_hooks.py`
- [x] Tagged v1.3.0
- **Rationale:** Enables observability without hardcoding it into every step. Example patterns: screenshot on every failure, push step timings to a metrics endpoint, send Telegram notification when workflow completes, integrate with OpenClaw cron/notify pipeline.

## Abandoned Approaches (documented for future reference)
- **vncdotool threaded API**: `captureScreen` hangs on macOS ARD (framebuffer timeout)
- **asyncvnc**: Screenshots all-black (encoding limitation)
- **vncdo stdin mode**: Can't interleave commands (batch-then-exit only)
- **Persistent connection pooling**: All tested persistent approaches fail on macOS ARD
