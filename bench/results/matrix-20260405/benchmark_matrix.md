# Vision Backend Benchmark Matrix

- Generated: 2026-04-05T23:26:43.144146+00:00
- Fixture: `/Users/openclaw/.openclaw/workspace/projects/worktrees/task-20260405-004-benchmark-matrix/bench/results/matrix-20260405/fixture.json`
- Image: `/Users/openclaw/.openclaw/workspace/projects/worktrees/task-20260405-004-benchmark-matrix/bench/results/matrix-20260405/fixture-click-lab.png`
- Cases: 10 (positive=8, negative=2)

## Summary

| Backend | Runnable | Pos Recall | Neg Specificity | Median Error (px) | P95 Error (px) | Median Latency (s) | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| moondream | yes | 1.000 | 0.000 | 2.000 | 60.564 | 4.400 | transformers + torch available |
| gemma4 | yes | 0.625 | 1.000 | 121.529 | 132.559 | 3.049 | Gemma endpoint reachable at http://127.0.0.1:8890/v1/models |
| anthropic | no | - | - | - | - | - | ANTHROPIC_API_KEY is not set |
| falcon | no | - | - | - | - | - | Model not cached locally: tiiuae/falcon-11b-vision-instruct |
| florence2 | no | - | - | - | - | - | Model not cached locally: microsoft/Florence-2-base-ft |
| sam2 | no | - | - | - | - | - | SAM2 is a segmentation model and is not text-grounded here (requires GroundingDINO/OWL-ViT + SAM2 integration). |

## Non-runnable backend actions

### anthropic
- Reason class: `missing_api_key`
- Reason: ANTHROPIC_API_KEY is not set
- Dry-run detect: `python3 bench/run_benchmark_matrix.py --fixture /Users/openclaw/.openclaw/workspace/projects/worktrees/task-20260405-004-benchmark-matrix/bench/results/matrix-20260405/fixture.json --backends anthropic --max-positive 1 --max-negative 0`
- Next steps:
  - `export ANTHROPIC_API_KEY=<your-key>`
  - `python3 bench/run_benchmark_matrix.py --fixture /Users/openclaw/.openclaw/workspace/projects/worktrees/task-20260405-004-benchmark-matrix/bench/results/matrix-20260405/fixture.json --backends anthropic --max-positive 1 --max-negative 0`

### falcon
- Reason class: `missing_model`
- Reason: Model not cached locally: tiiuae/falcon-11b-vision-instruct
- Dry-run detect: `python3 bench/run_benchmark_matrix.py --fixture /Users/openclaw/.openclaw/workspace/projects/worktrees/task-20260405-004-benchmark-matrix/bench/results/matrix-20260405/fixture.json --backends falcon --max-positive 1 --max-negative 0`
- Next steps:
  - `python3 - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('tiiuae/falcon-11b-vision-instruct')
PY`
  - `python3 bench/run_benchmark_matrix.py --fixture /Users/openclaw/.openclaw/workspace/projects/worktrees/task-20260405-004-benchmark-matrix/bench/results/matrix-20260405/fixture.json --backends falcon --max-positive 1 --max-negative 0`

### florence2
- Reason class: `missing_model`
- Reason: Model not cached locally: microsoft/Florence-2-base-ft
- Dry-run detect: `python3 bench/run_benchmark_matrix.py --fixture /Users/openclaw/.openclaw/workspace/projects/worktrees/task-20260405-004-benchmark-matrix/bench/results/matrix-20260405/fixture.json --backends florence2 --max-positive 1 --max-negative 0`
- Next steps:
  - `python3 - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('microsoft/Florence-2-base-ft')
PY`
  - `python3 bench/run_benchmark_matrix.py --fixture /Users/openclaw/.openclaw/workspace/projects/worktrees/task-20260405-004-benchmark-matrix/bench/results/matrix-20260405/fixture.json --backends florence2 --max-positive 1 --max-negative 0`

### sam2
- Reason class: `missing_grounding_stack`
- Reason: SAM2 is a segmentation model and is not text-grounded here (requires GroundingDINO/OWL-ViT + SAM2 integration).
- Dry-run detect: `python3 bench/run_benchmark_matrix.py --fixture /Users/openclaw/.openclaw/workspace/projects/worktrees/task-20260405-004-benchmark-matrix/bench/results/matrix-20260405/fixture.json --backends sam2 --max-positive 1 --max-negative 0`
- Next steps:
  - `python3 -m pip install git+https://github.com/facebookresearch/sam2.git`
  - `python3 -m pip install groundingdino-py`
  - `Implement text→box grounding stage, then feed boxes into SAM2 for mask refinement.`
  - `python3 bench/run_benchmark_matrix.py --fixture /Users/openclaw/.openclaw/workspace/projects/worktrees/task-20260405-004-benchmark-matrix/bench/results/matrix-20260405/fixture.json --backends sam2 --max-positive 1 --max-negative 0`
