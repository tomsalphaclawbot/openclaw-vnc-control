# VNC Click Accuracy Lab (Project-Local)

## Status

The click accuracy lab has been moved into this repository:

- `labs/vnc-click-lab/`

It is no longer anchored to `hello-world-nextjs` as the source-of-truth.

## Why this move

- Keeps validation assets beside the VNC bridge code.
- Makes click/key regression repeatable when `vnc-control.py` / `vnc-session.py` change.
- Avoids split ownership across unrelated projects.

## Contents

- `labs/vnc-click-lab/app/vnc-click-lab/page.tsx`
- `labs/vnc-click-lab/app/api/vnc-click-log/route.ts`
- `labs/vnc-click-lab/install-into-nextjs.sh`
- `labs/vnc-click-lab/README.md`

## How to use

1. Install routes into any Next.js app:

```bash
./labs/vnc-click-lab/install-into-nextjs.sh /path/to/nextjs-app
```

2. Run that app, then open:

- `http://localhost:<port>/vnc-click-lab`

3. Use VNC bridge commands to interact and verify logs at:

- `<next-app>/logs/vnc-click-events.jsonl`

## Automated regression script

Run the full 22-button sweep with:

```bash
python3 scripts/click-regression.py \
  --vnc-cwd /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control \
  --log-path /path/to/nextjs-app/logs/vnc-click-events.jsonl
```

What it does:
- computes deterministic button centers from the lab grid
- clicks each button via the VNC bridge
- verifies backend JSONL recorded the expected `button_click` label
- retries with small jitter offsets if needed
- exits non-zero on failures

Geometry can be overridden for different window/viewport calibrations:
`--section-left --section-top --section-width --section-height`.

Run field + keystroke regression with:

```bash
python3 scripts/input-key-regression.py \
  --vnc-cwd /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control \
  --log-path /path/to/nextjs-app/logs/vnc-click-events.jsonl
```

What it validates:
- `agent_input` receives typed text and logs `field_input`
- `agent_text_field` receives multiline text with Enter line breaks
- special keys + modifiers generate expected `field_keydown` events (Enter, Tab, Escape, Backspace, Delete, arrows, Shift/Meta/Control)

Run both regressions in one command:

```bash
scripts/run-all-regressions.sh \
  --vnc-cwd /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control \
  --log-path /path/to/nextjs-app/logs/vnc-click-events.jsonl
```

## Regression intent

This lab is the canonical surface for:
- full button click sweeps
- focus/typing tests
- key/modifier mapping verification
- coordinate-space sanity checks (`capture`/`native`/`normalized`)
