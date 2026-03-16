# VNC Click Accuracy Lab (Project-Local Standalone App)

## Status

The click lab now runs as its own standalone Next.js app inside this repository:

- `labs/vnc-click-lab/`

No external app is required.

## Why

- Keeps web test surface + VNC bridge in one project.
- Eliminates cross-project drift.
- Makes regression and calibration reproducible.

## Structure

- `labs/vnc-click-lab/app/vnc-click-lab/page.tsx`
- `labs/vnc-click-lab/app/api/vnc-click-log/route.ts`
- `labs/vnc-click-lab/app/page.tsx`
- `labs/vnc-click-lab/logs/vnc-click-events.jsonl` (runtime output)

## Start the lab

```bash
cd labs/vnc-click-lab
npm install
npm run dev
```

Open:
- `http://localhost:3015/vnc-click-lab`

## Telemetry for calibration

Event payload includes:
- `windowMetrics`
- `pointerMeta`
- `targetPoint`
- `targetError`

This supports page/client/screen/native mapping and affine correction fitting.

## Regression scripts

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

## One-shot runner

```bash
scripts/run-all-regressions.sh \
  --vnc-cwd /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control \
  --log-path /Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control/labs/vnc-click-lab/logs/vnc-click-events.jsonl
```
