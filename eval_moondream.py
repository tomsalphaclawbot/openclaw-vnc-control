#!/usr/bin/env python3
"""
Moondream2 evaluation for VNC coordinate precision.
Tests: can moondream locate UI elements (buttons, dialogs) in macOS screenshots
with bounding box accuracy suitable for automated clicking?

Usage:
    python3 eval_moondream.py --screenshot <path.jpg> --query "Allow button"
    python3 eval_moondream.py --live   # takes a fresh VNC screenshot and tests it
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

MODEL_ID = "vikhyatk/moondream2"
REVISION = "2025-06-21"  # latest stable tag

def load_model():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch
    print(f"Loading {MODEL_ID} (revision={REVISION})...", flush=True)
    t0 = time.time()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID, revision=REVISION, trust_remote_code=True,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
    )
    # Use MPS (Apple Silicon GPU) if available, else CPU
    device = "mps" if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available() else "cpu"
    model = model.to(device)
    model.eval()
    print(f"  Loaded in {time.time()-t0:.1f}s on {device}", flush=True)
    return model, tokenizer

def detect_element(model_tok, image_path: str, query: str) -> dict:
    """Ask moondream to locate an element. Returns bounding box and center coords."""
    from PIL import Image
    model, tokenizer = model_tok

    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    t0 = time.time()

    # Moondream2 v2 API: encode_image then detect
    enc = model.encode_image(img)
    result = model.detect(enc, query)["objects"]
    elapsed = time.time() - t0

    if not result:
        return {"found": False, "query": query, "elapsed_s": round(elapsed, 2), "image_size": [w, h]}

    # Coords are normalized 0..1
    box = result[0]
    x_min = box["x_min"] * w
    y_min = box["y_min"] * h
    x_max = box["x_max"] * w
    y_max = box["y_max"] * h
    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2

    return {
        "found": True,
        "query": query,
        "elapsed_s": round(elapsed, 2),
        "image_size": [w, h],
        "box_px": {"x_min": round(x_min), "y_min": round(y_min), "x_max": round(x_max), "y_max": round(y_max)},
        "center_px": {"x": round(cx), "y": round(cy)},
        "all_objects": result,
    }

def take_vnc_screenshot(out_path: str) -> bool:
    """Take a fresh VNC screenshot using vnc-control.py"""
    import subprocess
    script_dir = Path(__file__).parent
    env = os.environ.copy()
    env.setdefault("VNC_HOST", "127.0.0.1")
    env.setdefault("VNC_PORT", "5900")
    env.setdefault("VNC_USERNAME", "openclaw")

    result = subprocess.run(
        [sys.executable, str(script_dir / "vnc-control.py"),
         "screenshot", "--format", "jpeg", "--scale", "0.5", "--out", out_path],
        capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        print(f"VNC screenshot failed: {result.stderr}", file=sys.stderr)
        return False
    return True

def main():
    parser = argparse.ArgumentParser(description="Moondream2 VNC element detection eval")
    parser.add_argument("--screenshot", help="Path to existing screenshot")
    parser.add_argument("--live", action="store_true", help="Take fresh VNC screenshot")
    parser.add_argument("--query", default="Allow button", help="Element to locate")
    parser.add_argument("--queries", nargs="+", help="Multiple queries to test")
    parser.add_argument("--out", help="Save results JSON to this path")
    args = parser.parse_args()

    if args.live:
        screenshot_path = "/tmp/vnc-moondream-eval.jpg"
        print(f"Taking VNC screenshot -> {screenshot_path}")
        if not take_vnc_screenshot(screenshot_path):
            sys.exit(1)
    elif args.screenshot:
        screenshot_path = args.screenshot
    else:
        parser.error("Provide --screenshot <path> or --live")

    model_tok = load_model()

    queries = args.queries or [args.query]
    results = []
    for q in queries:
        print(f"\nQuery: '{q}'")
        r = detect_element(model_tok, screenshot_path, q)
        results.append(r)
        if r["found"]:
            c = r["center_px"]
            b = r["box_px"]
            print(f"  FOUND — center ({c['x']}, {c['y']}), box [{b['x_min']},{b['y_min']} → {b['x_max']},{b['y_max']}], {r['elapsed_s']}s")
        else:
            print(f"  NOT FOUND — {r['elapsed_s']}s")

    output = {"screenshot": screenshot_path, "results": results}
    print("\n--- JSON ---")
    print(json.dumps(output, indent=2))

    if args.out:
        Path(args.out).write_text(json.dumps(output, indent=2))
        print(f"\nSaved to {args.out}")

if __name__ == "__main__":
    main()
