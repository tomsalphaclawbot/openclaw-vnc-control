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

## Phase 2 — Session Daemon (v2) 🔧 IN PROGRESS
- [x] Daemon architecture: Unix socket server, vncdo subprocess dispatch
- [x] `vnc` wrapper script (PATH-accessible, resolves symlinks)
- [x] Keepalive: 25s center-area mouse jiggle (avoids hot corners)
- [x] Coordinate spaces: native / capture / normalized with auto-conversion
- [x] Screenshot via daemon working (JPEG 50%, ~350KB, ~0.6s)
- [x] Click, move, type, key via daemon working
- [ ] **Lock screen unlock reliability** — `key return` intermittent on macOS ARD
- [ ] Lock detection from screenshot analysis (is screen locked?)
- [ ] Auto-unlock macro with retry logic
- [ ] Disable macOS auto-lock via system settings (investigated: not MDM, not profiles)

## Phase 3 — Agent Skill Package ✅
- [x] `skill/SKILL.md` — AgentSkill spec with frontmatter
- [x] `skill/scripts/install.sh` — one-command setup
- [x] `skill/scripts/agent-loop-example.sh` — demo loop
- [x] Self-installed as OpenClaw native skill (symlinked)
- [x] TOOLS.md updated (references .env, not plaintext creds)

## Phase 4 — Hardening (next)
- [ ] Automated end-to-end smoke test script
- [ ] Test against non-macOS VNC server
- [ ] CI workflow
- [ ] `.env.example` template
- [ ] License file
- [ ] Tagged v0.1.0 release

## Phase 5 — API Wrapper (future)
- [ ] Local API session routing
- [ ] Mirror CLI commands in HTTP API
- [ ] Multi-session support

## Abandoned Approaches (documented for future reference)
- **vncdotool threaded API**: `captureScreen` hangs on macOS ARD (framebuffer timeout)
- **asyncvnc**: Screenshots all-black (encoding limitation)
- **vncdo stdin mode**: Can't interleave commands (batch-then-exit only)
- **Persistent connection pooling**: All tested persistent approaches fail on macOS ARD
