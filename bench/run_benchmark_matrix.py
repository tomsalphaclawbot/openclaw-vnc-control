#!/usr/bin/env python3
"""Run a reproducible backend benchmark matrix on a fixed screenshot fixture.

Backends:
- moondream (vnc-control integrated)
- gemma4 (vnc-control integrated, local OpenAI-compatible endpoint)
- anthropic (vnc-control integrated, API key required)
- florence2 (optional local HF backend)
- falcon (optional local HF backend)
- sam31 (optional local MLX backend)
- sam2 (legacy placeholder; not text-grounded in this harness)

Outputs written to --out-dir:
- benchmark_matrix.json
- benchmark_matrix.csv
- benchmark_matrix.md
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import re
import statistics
import subprocess
import time
import traceback
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DEFAULT_BACKENDS = ["auto", "moondream", "gemma4", "anthropic", "florence2", "falcon", "sam31"]


@dataclass
class Case:
    case_id: str
    query: str
    expected_found: bool
    expected_center: tuple[float, float] | None
    label: str | None = None
    kind: str | None = None


@dataclass
class Probe:
    backend: str
    runnable: bool
    reason_class: str
    reason: str
    dry_run_command: str
    next_steps: list[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    values = sorted(values)
    k = (len(values) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    return values[f] * (c - k) + values[c] * (k - f)


def model_cached(model_id: str) -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache

        cached = try_to_load_from_cache(model_id, "config.json")
        return isinstance(cached, str) and bool(cached)
    except Exception:
        return False


def import_vnc_module(repo_root: Path, gemma_endpoint: str | None) -> Any:
    if gemma_endpoint:
        os.environ["GEMMA4_ENDPOINT"] = gemma_endpoint

    vnc_path = repo_root / "vnc-control.py"
    spec = importlib.util.spec_from_file_location("vnc_control_bench", str(vnc_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {vnc_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def build_cases(fixture: dict[str, Any], max_positive: int, max_negative: int) -> list[Case]:
    elements = fixture.get("elements", [])
    positives: list[Case] = []

    allowed_kinds = {"button", "icon-button", "nav-link", "input", "select", "textarea"}

    for el in sorted(elements, key=lambda x: str(x.get("id", ""))):
        if len(positives) >= max_positive:
            break
        if el.get("id") == "report_coords_btn":
            continue
        kind = str(el.get("kind", "element"))
        if kind not in allowed_kinds:
            continue
        label = str(el.get("label", "")).strip()
        if not label:
            continue
        center = el.get("center_px") or el.get("center") or {}
        if "x" not in center or "y" not in center:
            continue

        if kind in {"button", "icon-button", "nav-link"}:
            query = f'button labeled "{label}"'
        elif kind in {"input", "textarea"}:
            query = f'input field labeled "{label}"'
        elif kind == "select":
            query = f'dropdown labeled "{label}"'
        else:
            query = f'element labeled "{label}"'

        positives.append(
            Case(
                case_id=f"pos-{el.get('id')}",
                query=query,
                expected_found=True,
                expected_center=(float(center["x"]), float(center["y"])),
                label=label,
                kind=kind,
            )
        )

    negatives: list[Case] = []
    for nq in fixture.get("negative_queries", [])[:max_negative]:
        negatives.append(
            Case(
                case_id=str(nq.get("id", f"neg-{len(negatives)+1}")),
                query=str(nq.get("query", "missing element")),
                expected_found=bool(nq.get("expected_found", False)),
                expected_center=None,
            )
        )

    return positives + negatives


def probe_backend(
    backend: str,
    fixture_path: Path,
    image_path: Path,
    vnc_module: Any,
    allow_model_download: bool,
    florence_model: str,
    falcon_model: str,
    sam31_model: str,
    gemma_endpoint: str,
) -> Probe:
    dry_run = (
        f"python3 bench/run_benchmark_matrix.py --fixture {fixture_path} "
        f"--backends {backend} --max-positive 1 --max-negative 0"
    )

    if backend == "auto":
        return Probe(
            backend,
            True,
            "ok",
            "auto chain is runtime-configured via vnc-control.py",
            dry_run,
            [],
        )

    if backend == "gemma4":
        endpoint = gemma_endpoint.rstrip("/")
        models_url = f"{endpoint}/v1/models"
        try:
            with urllib.request.urlopen(models_url, timeout=3) as resp:
                if resp.status == 200:
                    return Probe(backend, True, "ok", f"Gemma endpoint reachable at {models_url}", dry_run, [])
        except Exception as exc:
            return Probe(
                backend,
                False,
                "service_unreachable",
                f"Gemma endpoint not reachable at {models_url}: {exc}",
                dry_run,
                [
                    "bash /Users/openclaw/.openclaw/workspace/projects/gemma4-local/gemma4-server.sh",
                    f"curl -sS {models_url}",
                ],
            )

    if backend == "anthropic":
        if os.environ.get("ANTHROPIC_API_KEY"):
            return Probe(backend, True, "ok", "ANTHROPIC_API_KEY is set", dry_run, [])
        return Probe(
            backend,
            False,
            "missing_api_key",
            "ANTHROPIC_API_KEY is not set",
            dry_run,
            [
                "export ANTHROPIC_API_KEY=<your-key>",
                dry_run,
            ],
        )

    if backend == "moondream":
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401
        except Exception as exc:
            return Probe(
                backend,
                False,
                "missing_dependency",
                f"Moondream requires transformers + torch: {exc}",
                dry_run,
                [
                    "python3 -m pip install 'transformers==4.46.3' torch pillow einops",
                    dry_run,
                ],
            )
        return Probe(backend, True, "ok", "transformers + torch available", dry_run, [])

    if backend == "florence2":
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401
        except Exception as exc:
            return Probe(
                backend,
                False,
                "missing_dependency",
                f"Florence-2 requires transformers + torch: {exc}",
                dry_run,
                [
                    "python3 -m pip install 'transformers>=4.46.0' torch pillow",
                    f"python3 - <<'PY'\nfrom huggingface_hub import snapshot_download\nsnapshot_download('{florence_model}')\nPY",
                    dry_run,
                ],
            )

        cached = model_cached(florence_model)
        if cached or allow_model_download:
            return Probe(
                backend,
                True,
                "ok",
                "Florence-2 dependencies available" + (" (cached)" if cached else " (download allowed)"),
                dry_run,
                [],
            )

        return Probe(
            backend,
            False,
            "missing_model",
            f"Model not cached locally: {florence_model}",
            dry_run,
            [
                f"python3 - <<'PY'\nfrom huggingface_hub import snapshot_download\nsnapshot_download('{florence_model}')\nPY",
                dry_run,
            ],
        )

    if backend == "falcon":
        try:
            import falcon_perception  # noqa: F401
        except Exception as exc:
            return Probe(
                backend,
                False,
                "missing_dependency",
                f"Falcon backend requires local fork runtime (falcon_perception): {exc}",
                dry_run,
                [
                    "uv pip install -e 'projects/falcon-perception-fork[mlx]'",
                    f"python3 - <<'PY'\nfrom huggingface_hub import snapshot_download\nsnapshot_download('{falcon_model}')\nPY",
                    dry_run,
                ],
            )

        cached = model_cached(falcon_model)
        if cached or allow_model_download:
            # Execute a one-shot runtime smoke via vnc-control to catch platform/runtime failures
            # (for example macOS arm64 + triton/flex-attention incompatibilities).
            try:
                smoke = vnc_module.detect_element(str(image_path), "button", backend="falcon")
                smoke_err = str(smoke.get("error", "") or "")
                if smoke_err:
                    reason_class = "runtime_incompatible" if any(
                        tok in smoke_err.lower() for tok in ["triton", "mps", "cuda", "flexattention", "dynamo"]
                    ) else "runtime_error"
                    return Probe(
                        backend,
                        False,
                        reason_class,
                        f"Falcon runtime smoke failed: {smoke_err}",
                        dry_run,
                        [
                            "Use local fork MLX runtime on Apple Silicon.",
                            "Install: uv pip install -e 'projects/falcon-perception-fork[mlx]'.",
                            "For non-MLX environments, use Linux/CUDA torch runtime.",
                            dry_run,
                        ],
                    )
            except Exception as exc:
                return Probe(
                    backend,
                    False,
                    "runtime_error",
                    f"Falcon runtime smoke crashed: {exc}",
                    dry_run,
                    [
                        "Re-run falcon-only dry run and inspect traceback.",
                        dry_run,
                    ],
                )

            return Probe(
                backend,
                True,
                "ok",
                "Falcon deps/model available and runtime smoke passed"
                + (" (cached)" if cached else " (download allowed)"),
                dry_run,
                [],
            )
        return Probe(
            backend,
            False,
            "missing_model",
            f"Model not cached locally: {falcon_model}",
            dry_run,
            [
                f"python3 - <<'PY'\nfrom huggingface_hub import snapshot_download\nsnapshot_download('{falcon_model}')\nPY",
                dry_run,
            ],
        )

    if backend == "sam31":
        try:
            import numpy  # noqa: F401
            from mlx_vlm.utils import get_model_path  # noqa: F401
            from mlx_vlm.models.sam3.generate import Sam3Predictor  # noqa: F401
            from mlx_vlm.models.sam3_1.processing_sam3_1 import Sam31Processor  # noqa: F401
        except Exception as exc:
            return Probe(
                backend,
                False,
                "missing_dependency",
                f"SAM3.1 backend requires mlx_vlm + sam3_1 modules: {exc}",
                dry_run,
                [
                    "Use the gemma4-mlx environment with mlx_vlm installed.",
                    "pip install mlx-vlm",
                    dry_run,
                ],
            )

        cached = model_cached(sam31_model)
        if not (cached or allow_model_download):
            return Probe(
                backend,
                False,
                "missing_model",
                f"Model not cached locally: {sam31_model}",
                dry_run,
                [
                    f"python3 - <<'PY'\nfrom huggingface_hub import snapshot_download\nsnapshot_download('{sam31_model}')\nPY",
                    dry_run,
                ],
            )

        return Probe(
            backend,
            True,
            "ok",
            "SAM3.1 dependencies/model available" + (" (cached)" if cached else " (download allowed)"),
            dry_run,
            [],
        )

    if backend == "sam2":
        return Probe(
            backend,
            False,
            "missing_grounding_stack",
            "SAM2 is a segmentation model and is not text-grounded here (requires GroundingDINO/OWL-ViT + SAM2 integration).",
            dry_run,
            [
                "python3 -m pip install git+https://github.com/facebookresearch/sam2.git",
                "python3 -m pip install groundingdino-py",
                "Implement text→box grounding stage, then feed boxes into SAM2 for mask refinement.",
                dry_run,
            ],
        )

    return Probe(backend, False, "unknown_backend", f"Unknown backend: {backend}", dry_run, [])


def parse_fenced_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            block = parts[1].strip()
            if block.lower().startswith("json"):
                block = block[4:].strip()
            text = block
    return json.loads(text)


_LABELED_RE = re.compile(r"\blabeled\s+\"([^\"]+)\"", re.IGNORECASE)


def extract_labeled_text(query: str) -> str | None:
    m = _LABELED_RE.search(query or "")
    if not m:
        return None
    label = (m.group(1) or "").strip()
    return label or None


def _norm_token(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _append_note(existing: str | None, extra: str) -> str:
    if not existing:
        return extra
    if extra in existing:
        return existing
    return f"{existing}; {extra}"


def _parse_polygon_bbox(polygons: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(polygons, list):
        return None
    for poly in polygons:
        pts = poly
        if isinstance(poly, list) and poly and isinstance(poly[0], (list, tuple)):
            pts = poly[0]
        if not isinstance(pts, (list, tuple)) or len(pts) < 4:
            continue
        try:
            xs = [float(v) for v in pts[0::2]]
            ys = [float(v) for v in pts[1::2]]
        except Exception:
            continue
        if not xs or not ys:
            continue
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)
        # Ignore near-line degenerates that Florence can emit for misses.
        if (x_max - x_min) < 2 or (y_max - y_min) < 2:
            continue
        return x_min, y_min, x_max, y_max
    return None


def _extract_ocr_words(image_path: Path, ocr_cache: dict[str, Any]) -> list[dict[str, Any]]:
    key = str(image_path.resolve())
    if key in ocr_cache:
        return ocr_cache[key]

    cmd = ["tesseract", str(image_path), "stdout", "tsv", "--psm", "6"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12, check=False)
    except Exception:
        ocr_cache[key] = []
        return []

    if proc.returncode != 0 or not proc.stdout:
        ocr_cache[key] = []
        return []

    lines = proc.stdout.splitlines()
    if not lines:
        ocr_cache[key] = []
        return []

    header = lines[0].split("\t")
    idx = {name: i for i, name in enumerate(header)}
    required = {"left", "top", "width", "height", "conf", "text"}
    if not required.issubset(idx.keys()):
        ocr_cache[key] = []
        return []

    words: list[dict[str, Any]] = []
    for line in lines[1:]:
        cols = line.split("\t")
        if len(cols) < len(header):
            continue
        txt = cols[idx["text"]].strip()
        tok = _norm_token(txt)
        if not tok:
            continue
        try:
            conf = float(cols[idx["conf"]])
            left = float(cols[idx["left"]])
            top = float(cols[idx["top"]])
            width = float(cols[idx["width"]])
            height = float(cols[idx["height"]])
        except Exception:
            continue
        if conf < 20:
            continue
        words.append(
            {
                "text": txt,
                "token": tok,
                "conf": conf,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            }
        )

    ocr_cache[key] = words
    return words


def _find_label_in_ocr(image_path: Path, label: str, ocr_cache: dict[str, Any]) -> dict[str, Any] | None:
    words = _extract_ocr_words(image_path, ocr_cache)
    if not words:
        return None

    label_tokens = [_norm_token(t) for t in re.split(r"\s+", label.strip())]
    label_tokens = [t for t in label_tokens if t]
    if not label_tokens:
        return None

    n = len(label_tokens)
    best: dict[str, Any] | None = None
    for i in range(0, len(words) - n + 1):
        chunk = words[i : i + n]
        if [w["token"] for w in chunk] != label_tokens:
            continue
        left = min(w["left"] for w in chunk)
        top = min(w["top"] for w in chunk)
        right = max(w["left"] + w["width"] for w in chunk)
        bottom = max(w["top"] + w["height"] for w in chunk)
        score = sum(float(w["conf"]) for w in chunk) / n
        cand = {
            "box": {"x_min": left, "y_min": top, "x_max": right, "y_max": bottom},
            "center": {"x": (left + right) / 2.0, "y": (top + bottom) / 2.0},
            "confidence": round(score / 100.0, 3),
        }
        if best is None or cand["confidence"] > best["confidence"]:
            best = cand
    return best


def apply_label_ocr_postprocess(
    backend: str,
    image_path: Path,
    query: str,
    result: dict[str, Any],
    ocr_cache: dict[str, Any],
    enabled: bool,
) -> dict[str, Any]:
    if not enabled or backend not in {"falcon", "florence2", "sam31"}:
        return result

    label = extract_labeled_text(query)
    if not label:
        return result

    # OCR guard is reliable for simple human-readable labels; skip machine-ish IDs.
    if "_" in label:
        return result

    hint = _find_label_in_ocr(image_path, label, ocr_cache)
    found = bool(result.get("found"))
    pred = extract_center(result)

    if hint is None:
        if not found:
            return result
        patched = dict(result)
        patched["found"] = False
        patched["note"] = _append_note(result.get("note"), f"label OCR guard: text '{label}' not found")
        return patched

    dist = None
    if pred:
        dist = math.dist((pred[0], pred[1]), (hint["center"]["x"], hint["center"]["y"]))

    # Use OCR anchor if model missed, or predicted a far-away location.
    if (not found) or (dist is not None and dist > 140.0):
        patched = dict(result)
        patched["found"] = True
        patched["center"] = {"x": hint["center"]["x"], "y": hint["center"]["y"]}
        patched["center_px"] = {"x": hint["center"]["x"], "y": hint["center"]["y"]}
        patched["box"] = dict(hint["box"])
        patched["box_px"] = dict(hint["box"])
        patched["confidence"] = result.get("confidence") or hint.get("confidence")
        action = "fallback" if not found else "snap"
        patched["note"] = _append_note(result.get("note"), f"label OCR {action}: '{label}'")
        return patched

    return result


def run_florence2_detector(
    image_path: Path,
    query: str,
    state: dict[str, Any],
    model_id: str,
    allow_model_download: bool,
) -> dict[str, Any]:
    from PIL import Image
    from transformers import AutoModelForCausalLM, AutoProcessor
    import torch

    if "model" not in state:
        local_only = not allow_model_download
        processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True, local_files_only=local_only)
        model = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True, local_files_only=local_only)
        device = "mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu"
        model = model.to(device).eval()
        state.update({"model": model, "processor": processor, "device": device})

    model = state["model"]
    processor = state["processor"]
    device = state["device"]

    img = Image.open(image_path).convert("RGB")
    width, height = img.size
    task = "<OPEN_VOCABULARY_DETECTION>"
    target = extract_labeled_text(query) or query
    prompt = f"{task}{target}"

    t0 = time.time()
    inputs = processor(text=prompt, images=img, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        generated_ids = model.generate(**inputs, max_new_tokens=256, do_sample=False)
    text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    parsed = processor.post_process_generation(text, task=task, image_size=(width, height))
    elapsed = time.time() - t0

    detections = parsed.get(task, {}) if isinstance(parsed, dict) else {}
    bboxes = detections.get("bboxes") or []
    if bboxes:
        x_min, y_min, x_max, y_max = [float(v) for v in bboxes[0]]
    else:
        poly_box = _parse_polygon_bbox(detections.get("polygons") or [])
        if not poly_box:
            return {"found": False, "backend": "florence2", "elapsed_s": round(elapsed, 3), "note": "no boxes"}
        x_min, y_min, x_max, y_max = poly_box
    cx = (float(x_min) + float(x_max)) / 2.0
    cy = (float(y_min) + float(y_max)) / 2.0
    return {
        "found": True,
        "backend": "florence2",
        "elapsed_s": round(elapsed, 3),
        "center": {"x": cx, "y": cy},
        "box": {"x_min": float(x_min), "y_min": float(y_min), "x_max": float(x_max), "y_max": float(y_max)},
        "raw": parsed,
    }


def run_falcon_detector(
    image_path: Path,
    query: str,
    state: dict[str, Any],
    model_id: str,
    allow_model_download: bool,
) -> dict[str, Any]:
    from PIL import Image
    from transformers import AutoModelForVision2Seq, AutoProcessor
    import torch

    if "model" not in state:
        local_only = not allow_model_download
        processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True, local_files_only=local_only)
        model = AutoModelForVision2Seq.from_pretrained(model_id, trust_remote_code=True, local_files_only=local_only)
        device = "mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu"
        model = model.to(device).eval()
        state.update({"model": model, "processor": processor, "device": device})

    model = state["model"]
    processor = state["processor"]
    device = state["device"]

    img = Image.open(image_path).convert("RGB")

    prompt = (
        f'Locate "{query}" in this screenshot. '
        'Return only JSON: {"found":true,"x_min":<0-1>,"y_min":<0-1>,"x_max":<0-1>,"y_max":<0-1>} '
        'or {"found":false,"note":"why"}.'
    )

    t0 = time.time()
    inputs = processor(images=img, text=prompt, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        output_ids = model.generate(**inputs, max_new_tokens=180, do_sample=False)
    decoded = processor.batch_decode(output_ids, skip_special_tokens=True)[0]
    elapsed = time.time() - t0

    try:
        parsed = parse_fenced_json(decoded)
    except Exception as exc:
        return {
            "found": False,
            "backend": "falcon",
            "elapsed_s": round(elapsed, 3),
            "error": f"JSON parse failed: {exc}",
            "raw": decoded[:500],
        }

    if not parsed.get("found"):
        return {
            "found": False,
            "backend": "falcon",
            "elapsed_s": round(elapsed, 3),
            "note": parsed.get("note"),
        }

    with Image.open(image_path) as im:
        w, h = im.size

    x_min = float(parsed["x_min"]) * w
    y_min = float(parsed["y_min"]) * h
    x_max = float(parsed["x_max"]) * w
    y_max = float(parsed["y_max"]) * h
    return {
        "found": True,
        "backend": "falcon",
        "elapsed_s": round(elapsed, 3),
        "center": {"x": (x_min + x_max) / 2.0, "y": (y_min + y_max) / 2.0},
        "box": {"x_min": x_min, "y_min": y_min, "x_max": x_max, "y_max": y_max},
        "raw": parsed,
    }


def run_sam31_detector(
    image_path: Path,
    query: str,
    state: dict[str, Any],
    model_id: str,
    allow_model_download: bool,
) -> dict[str, Any]:
    import numpy as np
    from PIL import Image
    from mlx_vlm.utils import load_model, get_model_path
    from mlx_vlm.models.sam3.generate import Sam3Predictor
    from mlx_vlm.models.sam3_1.processing_sam3_1 import Sam31Processor

    if "predictor" not in state:
        if not allow_model_download and not model_cached(model_id):
            return {
                "found": False,
                "backend": "sam31",
                "error": f"Model not cached locally: {model_id}",
                "note": "Pass --allow-model-download or prefetch model into HF cache.",
            }

        model_path = get_model_path(model_id)
        model = load_model(model_path)
        processor = Sam31Processor.from_pretrained(str(model_path))
        predictor = Sam3Predictor(model, processor, score_threshold=0.2)
        state.update({"predictor": predictor})

    predictor = state["predictor"]
    img = Image.open(image_path).convert("RGB")

    t0 = time.time()
    target = extract_labeled_text(query)
    q_candidates = [query]
    if target:
        q_candidates = [target, query]
        if "input field" in query.lower():
            q_candidates.insert(0, f"input field {target}")
        elif "icon button" in query.lower():
            q_candidates.insert(0, f"icon {target}")
        elif "button" in query.lower() or "nav" in query.lower():
            q_candidates.insert(0, f"{target} button")

    out = None
    best_score = None
    best_box = None
    best_query = None
    for q in q_candidates:
        candidate = predictor.predict(img, text_prompt=q)
        scores = np.asarray(getattr(candidate, "scores", []))
        boxes = np.asarray(getattr(candidate, "boxes", []))
        if scores.size == 0 or boxes.size == 0:
            continue
        idx = int(scores.argmax())
        score = float(scores[idx])
        if best_score is None or score > best_score:
            best_score = score
            best_box = boxes[idx]
            best_query = q
            out = candidate
    elapsed = time.time() - t0

    if best_score is None or best_box is None:
        return {"found": False, "backend": "sam31", "elapsed_s": round(elapsed, 3), "note": "no detections"}

    x1, y1, x2, y2 = [float(v) for v in best_box.tolist()]
    all_scores = np.asarray(getattr(out, "scores", [])) if out is not None else np.asarray([])
    return {
        "found": True,
        "backend": "sam31",
        "elapsed_s": round(elapsed, 3),
        "center": {"x": (x1 + x2) / 2.0, "y": (y1 + y2) / 2.0},
        "box": {"x_min": x1, "y_min": y1, "x_max": x2, "y_max": y2},
        "confidence": float(best_score),
        "detections": int(all_scores.size),
        "query_used": best_query,
    }


def extract_center(result: dict[str, Any]) -> tuple[float, float] | None:
    center = result.get("center") or result.get("center_px")
    if isinstance(center, dict) and "x" in center and "y" in center:
        try:
            return float(center["x"]), float(center["y"])
        except Exception:
            return None
    return None


def run_backend_case(
    backend: str,
    case: Case,
    image_path: Path,
    vnc_module: Any,
    florence_state: dict[str, Any],
    falcon_state: dict[str, Any],
    sam31_state: dict[str, Any],
    florence_model: str,
    falcon_model: str,
    sam31_model: str,
    allow_model_download: bool,
    ocr_cache: dict[str, Any],
    label_ocr_postprocess: bool,
) -> dict[str, Any]:
    start = time.time()
    try:
        if backend in {"auto", "moondream", "gemma4", "anthropic", "falcon"}:
            result = vnc_module.detect_element(str(image_path), case.query, backend=backend)
        elif backend == "florence2":
            result = run_florence2_detector(image_path, case.query, florence_state, florence_model, allow_model_download)
        elif backend == "sam31":
            result = run_sam31_detector(image_path, case.query, sam31_state, sam31_model, allow_model_download)
        else:
            raise RuntimeError(f"Backend {backend} has no detector")
    except Exception as exc:
        return {
            "backend": backend,
            "case_id": case.case_id,
            "query": case.query,
            "expected_found": case.expected_found,
            "status": "error",
            "found": False,
            "elapsed_s": round(time.time() - start, 3),
            "error": f"{exc}",
            "traceback": traceback.format_exc(limit=2),
        }

    result = apply_label_ocr_postprocess(
        backend=backend,
        image_path=image_path,
        query=case.query,
        result=result,
        ocr_cache=ocr_cache,
        enabled=label_ocr_postprocess,
    )

    elapsed = float(result.get("elapsed_s", round(time.time() - start, 3)))
    found = bool(result.get("found", False))
    pred_center = extract_center(result)

    row: dict[str, Any] = {
        "backend": backend,
        "case_id": case.case_id,
        "query": case.query,
        "expected_found": case.expected_found,
        "found": found,
        "elapsed_s": round(elapsed, 3),
        "status": "ok",
        "label": case.label,
        "kind": case.kind,
    }

    if case.expected_center:
        row["expected_center_x"] = round(case.expected_center[0], 3)
        row["expected_center_y"] = round(case.expected_center[1], 3)

    if pred_center:
        row["pred_center_x"] = round(pred_center[0], 3)
        row["pred_center_y"] = round(pred_center[1], 3)

    if case.expected_found and found and case.expected_center and pred_center:
        dx = pred_center[0] - case.expected_center[0]
        dy = pred_center[1] - case.expected_center[1]
        row["error_px"] = round(math.sqrt(dx * dx + dy * dy), 3)
        row["error_dx_px"] = round(dx, 3)
        row["error_dy_px"] = round(dy, 3)
    elif case.expected_found and not found:
        row["error"] = result.get("error") or result.get("note") or "not found"

    if not case.expected_found:
        if found:
            row["classification"] = "fp"
        else:
            row["classification"] = "tn"
    else:
        if found:
            row["classification"] = "tp"
        else:
            row["classification"] = "fn"

    if result.get("error"):
        row["backend_error"] = str(result.get("error"))
    if result.get("note"):
        row["backend_note"] = str(result.get("note"))
    if result.get("confidence"):
        row["confidence"] = str(result.get("confidence"))

    return row


def summarize_backend(rows: list[dict[str, Any]], probe: Probe) -> dict[str, Any]:
    if not probe.runnable:
        return {
            "backend": probe.backend,
            "runnable": False,
            "reason_class": probe.reason_class,
            "reason": probe.reason,
            "dry_run_command": probe.dry_run_command,
            "next_steps": probe.next_steps,
            "attempted": 0,
        }

    attempted = len(rows)
    tp = sum(1 for r in rows if r.get("classification") == "tp")
    fn = sum(1 for r in rows if r.get("classification") == "fn")
    tn = sum(1 for r in rows if r.get("classification") == "tn")
    fp = sum(1 for r in rows if r.get("classification") == "fp")
    pos = tp + fn
    neg = tn + fp

    errors = [float(r["error_px"]) for r in rows if "error_px" in r]
    latencies = [float(r.get("elapsed_s", 0.0)) for r in rows if "elapsed_s" in r]

    return {
        "backend": probe.backend,
        "runnable": True,
        "attempted": attempted,
        "positive_cases": pos,
        "negative_cases": neg,
        "tp": tp,
        "fn": fn,
        "tn": tn,
        "fp": fp,
        "positive_recall": round(tp / pos, 4) if pos else None,
        "negative_specificity": round(tn / neg, 4) if neg else None,
        "median_error_px": round(statistics.median(errors), 3) if errors else None,
        "p95_error_px": round(percentile(errors, 0.95), 3) if errors else None,
        "median_latency_s": round(statistics.median(latencies), 3) if latencies else None,
        "reason_class": probe.reason_class,
        "reason": probe.reason,
        "dry_run_command": probe.dry_run_command,
        "next_steps": probe.next_steps,
    }


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    headers: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in headers:
                headers.append(k)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def write_markdown(
    path: Path,
    summaries: list[dict[str, Any]],
    probes: dict[str, Probe],
    fixture_path: Path,
    image_path: Path,
    cases: list[Case],
) -> None:
    lines: list[str] = []
    lines.append("# Vision Backend Benchmark Matrix")
    lines.append("")
    lines.append(f"- Generated: {utc_now()}")
    lines.append(f"- Fixture: `{fixture_path}`")
    lines.append(f"- Image: `{image_path}`")
    lines.append(f"- Cases: {len(cases)} (positive={sum(1 for c in cases if c.expected_found)}, negative={sum(1 for c in cases if not c.expected_found)})")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Backend | Runnable | Pos Recall | Neg Specificity | Median Error (px) | P95 Error (px) | Median Latency (s) | Notes |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---|")

    for s in summaries:
        note = s.get("reason", "")
        lines.append(
            "| "
            + " | ".join(
                [
                    str(s.get("backend")),
                    "yes" if s.get("runnable") else "no",
                    fmt(s.get("positive_recall")),
                    fmt(s.get("negative_specificity")),
                    fmt(s.get("median_error_px")),
                    fmt(s.get("p95_error_px")),
                    fmt(s.get("median_latency_s")),
                    str(note).replace("|", "\\|"),
                ]
            )
            + " |"
        )

    lines.append("")
    lines.append("## Non-runnable backend actions")
    lines.append("")
    for s in summaries:
        if s.get("runnable"):
            continue
        lines.append(f"### {s['backend']}")
        lines.append(f"- Reason class: `{s.get('reason_class')}`")
        lines.append(f"- Reason: {s.get('reason')}")
        lines.append(f"- Dry-run detect: `{s.get('dry_run_command')}`")
        steps = s.get("next_steps") or []
        if steps:
            lines.append("- Next steps:")
            for step in steps:
                lines.append(f"  - `{step}`")
        lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vision backend benchmark matrix runner")
    parser.add_argument("--fixture", required=True, help="Path to fixture JSON from capture_fixture.py")
    parser.add_argument("--backends", default=",".join(DEFAULT_BACKENDS), help="Comma-separated backends")
    parser.add_argument("--out-dir", default=None, help="Output directory (default: fixture parent)")
    parser.add_argument("--max-positive", type=int, default=8, help="Max positive cases")
    parser.add_argument("--max-negative", type=int, default=2, help="Max negative cases")
    parser.add_argument("--allow-model-download", action="store_true", help="Allow HF model downloads for optional backends")
    parser.add_argument("--florence-model", default="microsoft/Florence-2-base-ft", help="Florence model id")
    parser.add_argument("--falcon-model", default="tiiuae/Falcon-Perception-300M", help="Falcon model id")
    parser.add_argument("--sam31-model", default="mlx-community/sam3.1-bf16", help="SAM3.1 model id")
    parser.add_argument("--gemma-endpoint", default=os.environ.get("GEMMA4_ENDPOINT", "http://127.0.0.1:8890"))
    parser.add_argument(
        "--no-label-ocr-postprocess",
        action="store_true",
        help="Disable OCR label guard/snap fallback for falcon/florence2/sam31",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Keep falcon model selection consistent between this harness and vnc-control runtime.
    os.environ["FALCON_MODEL"] = args.falcon_model
    fixture_path = Path(args.fixture).resolve()
    fixture = load_json(fixture_path)

    image_rel = fixture.get("image", {}).get("path")
    if not image_rel:
        raise RuntimeError("Fixture missing image.path")
    image_path = Path(image_rel)
    if not image_path.is_absolute():
        image_path = (fixture_path.parent / image_path).resolve()

    # Some historical fixtures captured absolute paths from ephemeral worktrees.
    # If the absolute path no longer exists, fall back to fixture-dir basename.
    if not image_path.exists():
        fallback = (fixture_path.parent / Path(image_rel).name).resolve()
        if fallback.exists():
            image_path = fallback
        else:
            raise RuntimeError(f"Fixture image not found: {image_path}")

    backends = [b.strip() for b in args.backends.split(",") if b.strip()]
    out_dir = Path(args.out_dir).resolve() if args.out_dir else fixture_path.parent.resolve()
    ensure_dir(out_dir)

    cases = build_cases(fixture, max_positive=args.max_positive, max_negative=args.max_negative)

    repo_root = Path(__file__).resolve().parent.parent
    vnc = import_vnc_module(repo_root, args.gemma_endpoint)

    probes: dict[str, Probe] = {}
    all_rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []

    florence_state: dict[str, Any] = {}
    falcon_state: dict[str, Any] = {}
    sam31_state: dict[str, Any] = {}
    ocr_cache: dict[str, Any] = {}

    for backend in backends:
        probe = probe_backend(
            backend=backend,
            fixture_path=fixture_path,
            image_path=image_path,
            vnc_module=vnc,
            allow_model_download=args.allow_model_download,
            florence_model=args.florence_model,
            falcon_model=args.falcon_model,
            sam31_model=args.sam31_model,
            gemma_endpoint=args.gemma_endpoint,
        )
        probes[backend] = probe

        backend_rows: list[dict[str, Any]] = []
        if probe.runnable:
            for case in cases:
                row = run_backend_case(
                    backend=backend,
                    case=case,
                    image_path=image_path,
                    vnc_module=vnc,
                    florence_state=florence_state,
                    falcon_state=falcon_state,
                    sam31_state=sam31_state,
                    florence_model=args.florence_model,
                    falcon_model=args.falcon_model,
                    sam31_model=args.sam31_model,
                    allow_model_download=args.allow_model_download,
                    ocr_cache=ocr_cache,
                    label_ocr_postprocess=not args.no_label_ocr_postprocess,
                )
                backend_rows.append(row)
                all_rows.append(row)

        summaries.append(summarize_backend(backend_rows, probe))

    payload = {
        "generated_at": utc_now(),
        "fixture_path": str(fixture_path),
        "image_path": str(image_path),
        "config": {
            "backends": backends,
            "max_positive": args.max_positive,
            "max_negative": args.max_negative,
            "allow_model_download": args.allow_model_download,
            "florence_model": args.florence_model,
            "falcon_model": args.falcon_model,
            "sam31_model": args.sam31_model,
            "gemma_endpoint": args.gemma_endpoint,
            "label_ocr_postprocess": not args.no_label_ocr_postprocess,
        },
        "cases": [
            {
                "case_id": c.case_id,
                "query": c.query,
                "expected_found": c.expected_found,
                "expected_center": list(c.expected_center) if c.expected_center else None,
                "label": c.label,
                "kind": c.kind,
            }
            for c in cases
        ],
        "probes": {k: probe.__dict__ for k, probe in probes.items()},
        "backend_summaries": summaries,
        "rows": all_rows,
    }

    json_path = out_dir / "benchmark_matrix.json"
    csv_path = out_dir / "benchmark_matrix.csv"
    md_path = out_dir / "benchmark_matrix.md"

    write_json(json_path, payload)
    write_csv(all_rows, csv_path)
    write_markdown(md_path, summaries, probes, fixture_path, image_path, cases)

    print(
        json.dumps(
            {
                "ok": True,
                "json": str(json_path),
                "csv": str(csv_path),
                "md": str(md_path),
                "cases": len(cases),
                "backends": backends,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
