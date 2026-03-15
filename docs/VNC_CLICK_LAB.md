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

## Regression intent

This lab is the canonical surface for:
- full button click sweeps
- focus/typing tests
- key/modifier mapping verification
- coordinate-space sanity checks (`capture`/`native`/`normalized`)
