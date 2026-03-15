# openclaw-vnc-control — Task Board

Status: `TODO` | `IN_PROGRESS` | `DONE` | `BLOCKED`

## Coordination
- Local workspace task id: `task-20260315-001` (tracked in `/tasks/ACTIVE.md`)

---

## Sprint A — Groundwork ✅ DONE
- [DONE] Create project folder and public GitHub repo
- [DONE] README, ARCHITECTURE, ROADMAP, TASKS docs
- [DONE] Lock scope: single-host bridge, args/env credentials, CLI-first
- [TODO] Add license file
- [TODO] Add `.env.example` template

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
- [TODO] Lock detection from screenshot signature
- [TODO] Auto-unlock macro with retry logic
- [DONE] macOS screen lock timer fixed: screensaver idle 1800s, password delay 1800s, display sleep 0 on AC
  - `defaults -currentHost write com.apple.screensaver idleTime -int 1800`
  - `defaults write com.apple.screensaver askForPasswordDelay -int 1800`
  - Battery `displaysleep 2` still needs sudo to change; AC `displaysleep 0` is already correct
  - Hot corners all disabled (tl=1, bl=1, br=1)
  - Node TCC permissions dialog dismissed via VNC click

## Sprint E — Skill Package ✅ DONE
- [DONE] `skill/SKILL.md` — OpenClaw AgentSkill format with YAML frontmatter
- [DONE] `skill/scripts/install.sh` — one-command setup
- [DONE] `skill/scripts/agent-loop-example.sh` — demo agent loop
- [DONE] Symlinked into workspace skills dir
- [DONE] TOOLS.md credential security fix (removed plaintext, reference .env/Bitwarden)

## Sprint F — Hardening (next)
- [TODO] Automated e2e smoke test
- [TODO] Test against non-macOS VNC target
- [TODO] CI workflow
- [TODO] Tagged v0.1.0 release

---

## Known Issues

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | `key escape` times out on macOS ARD | Low | Documented, workaround in place |
| 2 | macOS auto-locks in ~1-2 min | High | **FIXED** — screensaver idle 1800s + password delay 1800s + display sleep 0 on AC |
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

## Immediate Next Actions
1. Fix lock screen unlock reliability (Issue #3)
2. Create `.env.example` template
3. Add license file
4. Commit all v2 changes and push
5. Update skill/SKILL.md for v2 daemon usage
