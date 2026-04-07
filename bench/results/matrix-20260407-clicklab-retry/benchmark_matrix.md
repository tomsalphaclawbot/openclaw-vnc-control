# Vision Backend Benchmark Matrix

- Generated: 2026-04-07T18:02:32.593092+00:00
- Fixture: `/Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control/bench/results/matrix-20260407-clicklab-retry/fixture.json`
- Image: `/Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control/bench/results/matrix-20260407-clicklab-retry/fixture-click-lab.png`
- Cases: 11 (positive=8, negative=3)

## Summary

| Backend | Runnable | Pos Recall | Neg Specificity | Median Error (px) | P95 Error (px) | Median Latency (s) | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| auto | yes | 1.000 | 0.000 | 2.138 | 129.739 | 0.609 | auto chain is runtime-configured via vnc-control.py |
| florence2 | yes | 1.000 | 0.667 | 2.229 | 129.455 | 0.575 | Florence-2 dependencies available (cached) |
| falcon | yes | 1.000 | 0.667 | 48.795 | 1007.661 | 1.096 | Falcon deps/model available and runtime smoke passed (cached) |
| sam31 | yes | 0.875 | 1.000 | 4.586 | 1108.214 | 9.806 | SAM3.1 dependencies/model available (cached) |
| moondream | yes | 1.000 | 0.000 | 2.000 | 60.564 | 4.621 | transformers + torch available |

## Non-runnable backend actions
