# VNC Click Accuracy Lab (Standalone)

This folder is the canonical, standalone web app for click testing in `openclaw-vnc-control`.

## What it contains

- `app/vnc-click-lab/page.tsx` — click/typing/key test UI
- `app/api/vnc-click-log/route.ts` — JSONL logger API
- `app/page.tsx` — simple launcher page
- `logs/vnc-click-events.jsonl` — runtime event log output (gitignored)

## Run locally

```bash
cd labs/vnc-click-lab
npm install
npm run dev
```

Open:
- `http://localhost:3015/`
- `http://localhost:3015/vnc-click-lab`

## Event types

- `button_click`
- `background_click`
- `field_focus`
- `field_input`
- `field_keydown`

## Calibration telemetry

Each click event includes:
- `windowMetrics` (scroll, inner/outer size, DPR, screenX/screenY)
- `pointerMeta` (page/client/screen + derived native coords)
- `targetPoint` (expected button center)
- `targetError` (actual minus expected deltas)

This enables page→screen conversion and offline click calibration fitting.

## Regression scripts

From project root:

```bash
python3 scripts/click-regression.py \
  --vnc-cwd /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control \
  --log-path /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control/labs/vnc-click-lab/logs/vnc-click-events.jsonl
```

```bash
python3 scripts/input-key-regression.py \
  --vnc-cwd /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control \
  --log-path /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control/labs/vnc-click-lab/logs/vnc-click-events.jsonl
```

```bash
python3 scripts/click-calibrator.py \
  --vnc-cwd /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control \
  --log-path /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control/labs/vnc-click-lab/logs/vnc-click-events.jsonl
```

```bash
scripts/run-all-regressions.sh \
  --vnc-cwd /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control \
  --log-path /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control/labs/vnc-click-lab/logs/vnc-click-events.jsonl
```
