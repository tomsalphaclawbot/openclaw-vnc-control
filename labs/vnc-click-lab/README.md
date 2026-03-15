# VNC Click Accuracy Lab

This lab is now housed in the `openclaw-vnc-control` project so click/typing validation lives with the VNC bridge code.

## Purpose

A deterministic browser test surface to validate:
- button click accuracy
- background click detection
- field focus/input behavior
- key press propagation (`Enter`, modifiers, arrows, etc.)

## Included Files

- `app/vnc-click-lab/page.tsx`
  - Test page with:
    - 22 fixed-position buttons
    - `agent_input` and `agent_text_field`
    - focus buttons for both fields
    - client-side event logging calls
- `app/api/vnc-click-log/route.ts`
  - API endpoint that appends JSONL events to `logs/vnc-click-events.jsonl`

## Event Types

The lab logs these event types:
- `button_click`
- `background_click`
- `field_focus`
- `field_input`
- `field_keydown`

## Use in a Next.js App

From a Next.js app root, copy the lab routes in:

```bash
mkdir -p app/vnc-click-lab app/api/vnc-click-log
cp /path/to/openclaw-vnc-control/labs/vnc-click-lab/app/vnc-click-lab/page.tsx app/vnc-click-lab/page.tsx
cp /path/to/openclaw-vnc-control/labs/vnc-click-lab/app/api/vnc-click-log/route.ts app/api/vnc-click-log/route.ts
```

Then run your app and open:

- `http://localhost:<port>/vnc-click-lab`

Logs are written to:

- `<next-app>/logs/vnc-click-events.jsonl`

## Automated button sweep

Use the project-level runner:

```bash
python3 scripts/click-regression.py \
  --vnc-cwd /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control \
  --log-path /path/to/nextjs-app/logs/vnc-click-events.jsonl
```

This validates all 22 buttons and exits non-zero on any mismatch.

## Notes

- The button layout is deterministic to make click regression reproducible.
- Keep logs out of git (`logs/` in `.gitignore`).
- This lab is intentionally simple and optimized for VNC-agent verification, not UI polish.
