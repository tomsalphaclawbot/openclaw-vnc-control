# Vision Benchmark Harness

Reproducible matrix benchmark for VNC vision backends.

## 1) Start click-lab

```bash
bash bench/start_click_lab.sh
```

Default URL: `http://127.0.0.1:3015/vnc-click-lab`

## 2) Capture deterministic fixture

```bash
python3 bench/capture_fixture.py \
  --base-url http://127.0.0.1:3015 \
  --page /vnc-click-lab \
  --out-dir bench/results \
  --run-id matrix-YYYYMMDD
```

Produces:
- `bench/results/<run-id>/fixture-click-lab.png`
- `bench/results/<run-id>/fixture.json`

## 3) Run backend matrix

Use the moondream venv (contains torch + transformers):

```bash
/Users/openclaw/.openclaw/workspace/.venvs/moondream/bin/python bench/run_benchmark_matrix.py \
  --fixture bench/results/<run-id>/fixture.json \
  --backends moondream,gemma4,anthropic,falcon,florence2,sam2
```

Outputs:
- `benchmark_matrix.json` (full raw data + probe details)
- `benchmark_matrix.csv` (per-case rows)
- `benchmark_matrix.md` (summary table + non-runnable actions)

## Notes

- Non-runnable backends are still included in output with `reason_class`, exact failure reason, dry-run detect command, and concrete next-step commands.
- Anthropic requires `ANTHROPIC_API_KEY`.
- Optional local HF backends (`falcon`, `florence2`) require cached model weights unless `--allow-model-download` is used.
