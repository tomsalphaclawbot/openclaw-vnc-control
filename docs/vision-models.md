# Vision Models for VNC Element Detection

Reference doc for the openclaw-vnc-control project. Covers every local/remote vision model
available for the `find_element`, `click_element`, and `assert_visible` commands.

---

## Decision Tree

```
Simple text? → cmd_read_text (Tesseract, 0.1s, free)
Need coords?
  ├── API cost OK? → find_element --model claude-opus-4-6 (best reasoning, ~3s, ~$0.01/call)
  └── No API cost?
        ├── Default → click_element (Moondream2 local, ~5-8s, MPS, no API)
        └── High volume / batch → Gemma 4 local server (26B MoE, ~2s/img, ~42 tok/s)
        └── Sub-1s needed → Florence-2 via CoreML (not yet implemented, Sprint H)
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

### Gemma 4 26B MoE (via local server) 🔬 TO BE TESTED

| Property | Value |
|----------|-------|
| Model | `mlx-community/gemma-4-26b-a4b-it-4bit` |
| Size | 26B MoE (4B active), ~15.5 GB RAM |
| Backend | mlx-vlm 0.4.4 + TurboQuant KV-3, MPS |
| Endpoint | `http://127.0.0.1:8890/v1/chat/completions` |
| Generation speed | ~42 tok/s (warm) |
| TTFT | ~1.8s at 1K context (mlx-vlm 0.4.4 chunked prefill) |
| Format | OpenAI-compatible JSON, multimodal (image + text) |
| Task | Needs testing for bounding-box extraction from screenshots |

**Approach for element detection:**
Send screenshot as base64 image + prompt: "Where is the [Allow button]? Return JSON: {x_min, y_min, x_max, y_max} normalized 0-1."

**Trade-offs vs Moondream2:**
- Pro: Much larger model, better reasoning, can handle complex/ambiguous queries
- Pro: Already running as a service — no separate model load
- Con: 15.5 GB RAM (leaves ~6 GB headroom on 32 GB)
- Con: If running Docker + MLX, need iogpu.wired_limit_mb cap active
- Con: No native grounding API — must parse JSON from text output (brittle)

**Test script:** `eval_gemma4_vision.py` (TODO)

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

## Benchmark Summary (as of 2026-04-04)

| Model | Latency | RAM | API Cost | Accuracy | Status |
|-------|---------|-----|----------|----------|--------|
| Moondream2 (local) | 4-8s | 1.5 GB | Free | Good | ✅ Integrated |
| Gemma 4 26B (server) | ~2s warm | 15.5 GB | Free | ? | 🔬 To test |
| Gemma 4 E4B (server) | ~0.5s warm | 5.2 GB | Free | ? | 🔬 To test |
| Florence-2 | <1s | 1-3 GB | Free | ? | 🔲 Not installed |
| Claude Opus | 2-4s | 0 | ~$0.01/call | Excellent | ✅ Integrated (fallback) |
| Claude Haiku | 1-2s | 0 | ~$0.002/call | Good | ✅ Available |

---

## Integration Guide

### Adding a new vision backend

1. Add a `_detect_<model>(image_path, query) -> dict` function in `vnc-control.py`
2. Return format: `{"found": bool, "center_px": {"x": int, "y": int}, "box_px": {...}, "elapsed_s": float}`
3. Wire into `cmd_click_element` via backend selector arg (`--backend moondream|gemma4|florence2|remote`)
4. Add eval script `eval_<model>.py` with screenshot test harness
5. Update this doc

### Running `click_element` with a specific backend

```bash
# Default (Moondream2 local, no API)
python vnc-control.py click_element "Allow button"

# Force remote API fallback
VNC_VISION_MODEL=claude-opus-4-6 python vnc-control.py click_element "Allow button" --backend remote

# Gemma4 (once eval_gemma4_vision.py is wired in)
python vnc-control.py click_element "Allow button" --backend gemma4
```

---

## Environment Setup

```bash
# Moondream2 venv
uv venv .venvs/moondream --python 3.11
uv pip install --python .venvs/moondream "transformers==4.46.3" torch pillow einops

# Gemma4 server (already set up)
bash ../gemma4-local/gemma4-server.sh   # starts on port 8890
```

---

*Last updated: 2026-04-04 | Sprint H*
