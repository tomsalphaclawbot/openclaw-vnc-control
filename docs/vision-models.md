# Vision Models for VNC Element Detection

Reference for `vnc-control.py` detection backends used by `click_element`, `find_element`, `wait_for`, and `assert_visible`.

## Current local backend strategy

Default backend mode is now **auto**:

- `VNC_VISION_BACKEND_DEFAULT=auto`
- `VNC_VISION_BACKEND_CHAIN=florence2,falcon,sam31`
- `VNC_VISION_AUTO_MOONDREAM_LABEL_FALLBACK=1`

So the system tries the strongest local backends first.
`moondream` remains available as an explicit/manual backend for hard recall cases, and can be used as an OCR-guarded last-chance auto fallback when `VNC_VISION_AUTO_MOONDREAM_LABEL_FALLBACK=1`.
You can still force a specific backend with `--backend <name>`. 

## Supported backends

- `florence2` (local, transformers)
- `falcon` (local, Falcon fork + MLX path on Apple Silicon)
- `sam31` (local, mlx-vlm)
- `moondream` (local, transformers)
- `gemma4` (local server)
- `anthropic` / `remote` (API)
- `auto` (configured chain)

## Benchmark summary (matrix-20260407-four-models)

Fixture and artifacts are committed under:
- `bench/results/matrix-20260407-four-models/fixture.json`
- `bench/results/matrix-20260407-four-models/fixture-click-lab.png`
- `bench/results/matrix-20260407-four-models/benchmark_matrix.{json,csv,md}`

Measured (`8` positive + `2` negative):

| Backend | Pos Recall | Neg Specificity | Median Error (px) | P95 Error (px) | Median Latency (s) |
|---|---:|---:|---:|---:|---:|
| moondream | 1.000 | 0.000 | 2.000 | 60.564 | 4.311 |
| falcon | 1.000 | 1.000 | 48.795 | 1007.661 | 1.089 |
| florence2 | 1.000 | 1.000 | 2.229 | 129.455 | 0.580 |
| sam31 | 0.875 | 1.000 | 4.586 | 1108.214 | 9.681 |

### Practical order (this host)

1. **florence2**
2. **falcon**
3. **sam31**
4. **moondream** (great recall, weaker no-target rejection)

## Runtime examples

```bash
# Default (auto chain)
python vnc-control.py click_element "Allow button"

# Force a specific backend
python vnc-control.py click_element "Allow button" --backend florence2
python vnc-control.py click_element "Allow button" --backend falcon
python vnc-control.py click_element "Allow button" --backend sam31
python vnc-control.py click_element "Allow button" --backend moondream
```

## Re-running four-model benchmark

```bash
bash bench/run_four_model_matrix.sh matrix-YYYYMMDD-four-models bench/results/matrix-20260405/fixture.json
```

To allow model auto-download during runtime/bench:

```bash
export VNC_VISION_ALLOW_MODEL_DOWNLOAD=1
```
