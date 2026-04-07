# Vision Backend Benchmark Matrix

- Generated: 2026-04-07T14:37:32.222852+00:00
- Fixture: `/Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control/bench/results/matrix-20260407-four-models/fixture.json`
- Image: `/Users/openclaw/.openclaw/workspace/projects/openclaw-vnc-control/bench/results/matrix-20260407-four-models/fixture-click-lab.png`
- Cases: 10 (positive=8, negative=2)

## Summary

| Backend | Runnable | Pos Recall | Neg Specificity | Median Error (px) | P95 Error (px) | Median Latency (s) | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| moondream | yes | 1.000 | 0.000 | 2.000 | 60.564 | 4.311 | transformers + torch available |
| falcon | yes | 1.000 | 1.000 | 48.795 | 1007.661 | 1.089 | Falcon deps/model available and runtime smoke passed (cached) |
| florence2 | yes | 1.000 | 1.000 | 2.229 | 129.455 | 0.580 | Florence-2 dependencies available (cached) |
| sam31 | yes | 0.875 | 1.000 | 4.586 | 1108.214 | 9.681 | SAM3.1 dependencies/model available (cached) |

## Non-runnable backend actions
