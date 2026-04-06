# Vision Models for VNC Element Detection

Reference doc for the openclaw-vnc-control project. Covers every local/remote vision model
available for the `find_element`, `click_element`, and `assert_visible` commands.

---

## Decision Tree

```
Simple text? → cmd_read_text (Tesseract, 0.1s, free)
Need coords?
  ├── API cost OK? → find_element --backend anthropic (best reasoning, ~3s, paid)
  └── No API cost?
        ├── Default → click_element --backend moondream (local, stable)
        ├── Better reasoning local → --backend gemma4 (local server)
        ├── Falcon experiment → --backend falcon (currently blocked on macOS due triton dependency)
        └── Sub-1s needed → Florence-2 via CoreML (not yet implemented)
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

### Gemma 4 26B MoE (via local server) ✅ INTEGRATED

| Property | Value |
|----------|-------|
| Model | `mlx-community/gemma-4-26b-a4b-it-4bit` |
| Size | 26B MoE (4B active), ~15.5 GB RAM |
| Backend | mlx-vlm 0.4.4 + TurboQuant KV-3, MPS |
| Endpoint | `http://127.0.0.1:8890/v1/chat/completions` |
| Generation speed | ~42 tok/s (warm) |
| TTFT | ~1.8s at 1K context (mlx-vlm 0.4.4 chunked prefill) |
| Format | OpenAI-compatible JSON, multimodal (image + text) |
| Task | Bounding-box extraction via JSON prompt + normalized coord parsing |

**Approach for element detection:**
Send screenshot as base64 image + prompt: "Where is the [Allow button]? Return JSON: {x_min, y_min, x_max, y_max} normalized 0-1."

**Trade-offs vs Moondream2:**
- Pro: Much larger model, better reasoning, can handle complex/ambiguous queries
- Pro: Already running as a service — no separate model load
- Con: 15.5 GB RAM (leaves ~6 GB headroom on 32 GB)
- Con: If running Docker + MLX, need iogpu.wired_limit_mb cap active
- Con: No native grounding API — must parse JSON from text output (brittle)

**Test script:** `eval_gemma4_vision.py`

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

### Falcon Perception ⚠️ INTEGRATED WITH CLEAN FALLBACK

| Property | Value |
|----------|-------|
| Model | `tiiuae/Falcon-Perception` |
| Backend | `transformers` (`trust_remote_code`) |
| Output | normalized center+size (`xy` + `hw`) + optional `mask_rle` |
| Integration | `detect_element()` + `click_element --backend falcon` + `find_element/wait_for/assert_visible --backend falcon` |
| Eval harness | `eval_falcon.py` |

**Apple Silicon status (2026-04-05):** upstream Falcon-Perception model code requires `triton` at load time. On macOS arm64 this dependency is typically unavailable, so the backend returns `found=false` with explicit setup guidance instead of crashing.

**Fallback guidance emitted by backend:**
- run Falcon in Linux/CUDA with `triton` installed, or
- use `moondream` / `gemma4` local backends on Apple Silicon.

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
**Current status:** minimal scaffold script exists (`eval_florence2.py`) to unblock local runs.

```bash
python3 eval_florence2.py --screenshot /tmp/screen.jpg --query "Allow button"
```

Known remaining work:
- Validate `parsed` output schema across multiple screenshots
- Measure latency/accuracy vs Moondream2 and Gemma4 on click-lab scenarios
- Decide whether to wire a `_detect_florence2()` backend into `detect_element()`

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

## Benchmark Summary (as of 2026-04-05)

### Targeted run: Falcon vs Moondream (same screenshot + prompts)

Command:
```bash
/Users/openclaw/.openclaw/workspace/.venvs/moondream/bin/python eval_falcon.py \
  --screenshot /tmp/falcon-bench.jpg \
  --queries cat person \
  --runs 1 \
  --out /tmp/falcon-benchmark.json
```

| Backend | Found rate | Avg latency (s) | IoU vs Moondream ref | Center delta vs ref (px) | Notes |
|---|---:|---:|---:|---:|---|
| Moondream | 0.50 (1/2) | 12.84 | 1.00 | 0.0 | Reference backend |
| Falcon | 0.00 (0/2) | 0.00* | n/a | n/a | Failed cleanly at load: missing `triton` |

\* Falcon latency is effectively setup-failure path latency (no inference executed).

### Matrix snapshot

| Model | Latency | RAM | API Cost | Accuracy | Status |
|-------|---------|-----|----------|----------|--------|
| Moondream2 (local) | 4-16s observed | ~1.5 GB | Free | Good | ✅ Integrated |
| Gemma 4 26B (server) | ~2s warm | ~15.5 GB | Free | Good on hard negatives | ✅ Integrated |
| Falcon Perception | blocked locally | n/a | Free | n/a on this host | ⚠️ Integrated fallback (triton blocker) |
| Florence-2 | <1s target | 1-3 GB | Free | ? | 🔲 Not installed |
| Gemma 4 E4B (server) | ~0.5s warm | 5.2 GB | Free | ? | 🔬 To test |
| Claude Opus | 2-4s | 0 | ~$0.01/call | Excellent | ✅ Integrated (fallback) |

---

## Integration Guide

### Adding a new vision backend

1. Add a `_detect_<model>(image_path, query) -> dict` function in `vnc-control.py`
2. Return format: `{"found": bool, "center_px": {"x": int, "y": int}, "box_px": {...}, "elapsed_s": float}`
3. Wire into `detect_element()` dispatcher and CLI selectors (`--backend moondream|gemma4|falcon|anthropic|remote`)
4. Add eval script `eval_<model>.py` with screenshot test harness
5. Update this doc

### Running `click_element` with a specific backend

```bash
# Default (Moondream2 local, no API)
python vnc-control.py click_element "Allow button"

# Force remote API fallback
VNC_VISION_MODEL=claude-opus-4-6 python vnc-control.py click_element "Allow button" --backend remote

# Gemma4
python vnc-control.py click_element "Allow button" --backend gemma4

# Falcon (will fail cleanly with setup guidance if triton is unavailable)
python vnc-control.py click_element "Allow button" --backend falcon
```

---

## Environment Setup

```bash
# Moondream2 venv
uv venv .venvs/moondream --python 3.11
uv pip install --python .venvs/moondream "transformers==4.46.3" torch pillow einops pycocotools

# Falcon note: upstream currently requires triton at runtime.
# On Apple Silicon/macOS this is often unavailable; use Linux/CUDA host for true Falcon inference.

# Gemma4 server (already set up)
bash ../gemma4-local/gemma4-server.sh   # starts on port 8890
```

---

*Last updated: 2026-04-05 | Sprint H (Falcon backend integration + benchmark evidence)*
