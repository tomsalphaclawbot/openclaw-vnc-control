# Vision Models for VNC Element Detection

Reference doc for the openclaw-vnc-control project. Covers every local/remote vision model
available for the `find_element`, `click_element`, and `assert_visible` commands.

---

## Decision Tree

```
Simple text? → cmd_read_text (Tesseract, 0.1s, free)
Need coords?
  ├── Safety-critical / avoid false positives? → gemma4 (best measured specificity, ~3s)
  ├── Element definitely present / max recall? → moondream (best measured recall, ~4.5s)
  ├── API fallback available? → anthropic (requires ANTHROPIC_API_KEY)
  └── Exploring new local options? → florence2 / falcon / sam2 (matrix probe + setup required)
```

---

## Local Models (no API call, no cost)

### Moondream2 ✅ INTEGRATED (`click_element`)

| Property | Value |
|----------|-------|
| Model | `vikhyatk/moondream2` (revision `2025-06-21`) |
| Size | ~1.86B params, ~1.5 GB RAM |
| Backend | `transformers` 4.x + MPS (Apple Silicon GPU) |
| Load time | ~3s (cached in-process after first call) |
| Detection latency | ~4-8s per query |
| API | `model.encode_image(img)` → `model.detect(enc, query)` |
| Output | Normalized bounding boxes `{x_min, y_min, x_max, y_max}` (0..1) |
| Accuracy | High for named UI elements ("Allow button", "dialog box") |
| Integration | `click_element` command, `eval_moondream.py` |
| Venv | `.venvs/moondream` (transformers==4.46.3) |

**Usage:**
```bash
python vnc-control.py click_element "Allow button"
python eval_moondream.py --screenshot screen.jpg --queries "Allow button" "Cancel"
```

**Known issues:**
- `moondream` PyPI package (cloud client) ≠ local inference; install `transformers==4.46.3`
- transformers 5.x breaks `HfMoondream` (`all_tied_weights_keys` AttributeError) — pin to 4.46.3
- `PhotonVL` (moondream3) requires CUDA — not usable on Mac
- Revision tags use date format (`2025-06-21`), not semver

---

### Gemma 4 26B MoE (via local server) ✅ MEASURED (2026-04-05)

| Property | Value |
|----------|-------|
| Model | `mlx-community/gemma-4-26b-a4b-it-4bit` |
| Size | 26B MoE (4B active), ~15.5 GB RAM |
| Backend | mlx-vlm 0.4.4 + TurboQuant KV-3, MPS |
| Endpoint | `http://127.0.0.1:8890/v1/chat/completions` |
| Generation speed | ~42 tok/s (warm) |
| TTFT | ~1.8s at 1K context (mlx-vlm 0.4.4 chunked prefill) |
| Format | OpenAI-compatible JSON, multimodal (image + text) |
| Task | Bounding-box extraction from screenshots benchmarked via matrix harness |

**Approach for element detection:**
Send screenshot as base64 image + prompt: "Where is the [Allow button]? Return JSON: {x_min, y_min, x_max, y_max} normalized 0-1."

**Trade-offs vs Moondream2:**
- Pro: Much larger model, better reasoning, can handle complex/ambiguous queries
- Pro: Already running as a service — no separate model load
- Con: 15.5 GB RAM (leaves ~6 GB headroom on 32 GB)
- Con: If running Docker + MLX, need iogpu.wired_limit_mb cap active
- Con: No native grounding API — must parse JSON from text output (brittle)

**Benchmark harness:** `bench/run_benchmark_matrix.py` (measured in `bench/results/matrix-20260405/`)

---

### Gemma 4 E4B (4.5B effective)

| Property | Value |
|----------|-------|
| Model | `mlx-community/gemma-4-e4b-it-4bit` |
| Size | ~5.2 GB RAM |
| Backend | mlx-vlm 0.4.4, MPS |
| Generation speed | ~54 tok/s |
| TTFT | ~0.3s |
| Use case | High-volume batch, low RAM budget |

Same approach as 26B but faster and lighter. Quality lower but fine for simple UI elements.

---

### Florence-2 (Microsoft) 🔲 NOT YET EVALUATED

| Property | Value |
|----------|-------|
| Model | `microsoft/Florence-2-base` (~232M) or `-large` (~770M) |
| Backend | transformers or CoreML |
| Latency | Sub-second (design target) |
| Tasks | Object detection, OCR, captioning, grounding |
| Output | Bounding boxes via `<OPEN_VOCABULARY_DETECTION>` task token |

**Why interesting:** Smallest model that can do grounding. Fast enough for real-time use.
**Blocker:** Not yet installed or tested. Sprint H task.

---

## Remote Models (API call required)

### Anthropic Claude (current default for `find_element`)

| Property | Value |
|----------|-------|
| Models | `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-*` |
| Latency | ~2-4s |
| Cost | ~$0.005–0.015 per screenshot |
| Integration | `find_element`, `wait_for`, `assert_visible` |
| Output | Free-form JSON with x, y center + optional bbox + reasoning |
| Strength | Best reasoning — finds elements even with indirect descriptions |
| Weakness | API cost, latency, requires ANTHROPIC_API_KEY |

```bash
python vnc-control.py find_element "the confirmation dialog's primary action button"
```

---

## Benchmark Summary (measured 2026-04-05)

Matrix run used a deterministic Click Lab fixture (`8` positive + `2` negative prompts):
- Fixture: `bench/results/matrix-20260405/fixture.json`
- Image: `bench/results/matrix-20260405/fixture-click-lab.png`
- Raw artifacts: `benchmark_matrix.json`, `benchmark_matrix.csv`, `benchmark_matrix.md`

| Backend | Runnable | Pos Recall | Neg Specificity | Median Error (px) | P95 Error (px) | Median Latency (s) | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| moondream | yes | 1.000 | 0.000 | 2.000 | 60.564 | 4.400 | ✅ Measured |
| gemma4 | yes | 0.625 | 1.000 | 121.529 | 132.559 | 3.049 | ✅ Measured |
| anthropic | no | - | - | - | - | - | ⛔ Missing `ANTHROPIC_API_KEY` |
| falcon | no | - | - | - | - | - | ⛔ Model not cached (`tiiuae/falcon-11b-vision-instruct`) |
| florence2 | no | - | - | - | - | - | ⛔ Model not cached (`microsoft/Florence-2-base-ft`) |
| sam2 | no | - | - | - | - | - | ⛔ No text-grounding pipeline wired |

### Measured recommendation order (this environment)

For production click workflows, prioritize safety over raw recall:

1. **gemma4** — fastest measured backend + zero false positives on negative prompts.
2. **moondream** — excellent recall/precision on positive elements, but high hallucination risk when element is absent.
3. **anthropic** (when key configured) — use as tie-breaker/fallback for ambiguous cases.
4. **florence2** — next local candidate after model download; rerun matrix before promotion.
5. **falcon** — experimental; only promote after measured matrix results exist.
6. **sam2** — not directly comparable until text→box grounding is integrated.

---

## Integration Guide

### Adding a new vision backend

1. Add a `_detect_<model>(image_path, query) -> dict` function in `vnc-control.py`
2. Return format: `{"found": bool, "center_px": {"x": int, "y": int}, "box_px": {...}, "elapsed_s": float}`
3. Wire into `detect_element()` + `cmd_click_element` backend selector (`--backend moondream|gemma4|anthropic`; `remote` remains an alias for anthropic)
4. Add eval script `eval_<model>.py` with screenshot test harness
5. Update this doc

### Running `click_element` with a specific backend

```bash
# Default (Moondream2 local, no API)
python vnc-control.py click_element "Allow button"

# Force Anthropic API backend (remote alias still supported)
VNC_VISION_MODEL=claude-opus-4-6 python vnc-control.py click_element "Allow button" --backend anthropic

# Gemma4 local backend
python vnc-control.py click_element "Allow button" --backend gemma4
```

---

## Reproducible Benchmark Commands

```bash
# 1) Start fixture app
bash bench/start_click_lab.sh

# 2) Capture deterministic fixture + ground truth
python3 bench/capture_fixture.py \
  --base-url http://127.0.0.1:3015 \
  --page /vnc-click-lab \
  --out-dir bench/results \
  --run-id matrix-YYYYMMDD

# 3) Run full matrix
/Users/openclaw/.openclaw/workspace/.venvs/moondream/bin/python bench/run_benchmark_matrix.py \
  --fixture bench/results/matrix-YYYYMMDD/fixture.json \
  --backends moondream,gemma4,anthropic,falcon,florence2,sam2
```

## Environment Setup

```bash
# Moondream2 venv
uv venv .venvs/moondream --python 3.11
uv pip install --python .venvs/moondream "transformers==4.46.3" torch pillow einops

# Gemma4 server (already set up)
bash ../gemma4-local/gemma4-server.sh   # starts on port 8890
```

---

*Last updated: 2026-04-05 | Sprint I benchmark matrix run (`matrix-20260405`)*
