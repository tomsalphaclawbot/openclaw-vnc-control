#!/usr/bin/env python3
"""
Florence-2 evaluation scaffold for VNC element grounding.

Status: minimal scaffold (Sprint H follow-up).
- Loads Florence-2 model/processor when dependencies are available.
- Runs one-shot open-vocabulary detection prompt for a screenshot.
- Prints raw + parsed output to unblock local benchmarking.

Usage:
  python3 eval_florence2.py --screenshot /tmp/screen.jpg --query "Allow button"
  python3 eval_florence2.py --live --query "Continue"

Suggested install:
  pip install "transformers>=4.47" torch pillow
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_MODEL = os.environ.get("FLORENCE2_MODEL", "microsoft/Florence-2-base")


def take_vnc_screenshot(out_path: str) -> bool:
    script_dir = Path(__file__).parent
    env = os.environ.copy()
    env.setdefault("VNC_HOST", "127.0.0.1")
    env.setdefault("VNC_PORT", "5900")
    env.setdefault("VNC_USERNAME", "openclaw")

    result = subprocess.run(
        [sys.executable, str(script_dir / "vnc-control.py"),
         "screenshot", "--format", "jpeg", "--scale", "0.5", "--out", out_path],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
    return result.returncode == 0


def run_detection(model_id: str, image_path: str, query: str) -> dict:
    t0 = time.time()

    try:
        import torch
        from PIL import Image
        from transformers import AutoModelForCausalLM, AutoProcessor
    except Exception as e:
        return {
            "ok": False,
            "error": f"Missing dependency: {e}",
            "install": "pip install 'transformers>=4.47' torch pillow",
        }

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device in ("cuda", "mps") else torch.float32

    try:
        processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True).to(device)
        model.eval()
    except Exception as e:
        return {"ok": False, "error": f"Model load failed: {e}"}

    image = Image.open(image_path).convert("RGB")
    w, h = image.size

    task_token = "<OPEN_VOCABULARY_DETECTION>"
    prompt = f"{task_token}{query}"

    try:
        inputs = processor(text=prompt, images=image, return_tensors="pt")
        inputs = {k: (v.to(device) if hasattr(v, "to") else v) for k, v in inputs.items()}

        generated_ids = model.generate(
            **inputs,
            max_new_tokens=256,
            do_sample=False,
            num_beams=1,
        )
        generated_text = processor.batch_decode(generated_ids, skip_special_tokens=False)[0]

        parsed = None
        if hasattr(processor, "post_process_generation"):
            try:
                parsed = processor.post_process_generation(
                    generated_text,
                    task=task_token,
                    image_size=(w, h),
                )
            except Exception:
                parsed = None

        return {
            "ok": True,
            "model": model_id,
            "query": query,
            "image": image_path,
            "image_size": [w, h],
            "elapsed_s": round(time.time() - t0, 3),
            "task": task_token,
            "raw_text": generated_text,
            "parsed": parsed,
            "note": "Scaffold output: inspect `parsed` schema and wire into detect_element once stable.",
        }
    except Exception as e:
        return {
            "ok": False,
            "model": model_id,
            "query": query,
            "image": image_path,
            "elapsed_s": round(time.time() - t0, 3),
            "error": f"Inference failed: {e}",
        }


def main() -> None:
    ap = argparse.ArgumentParser(description="Florence-2 grounding eval scaffold")
    ap.add_argument("--screenshot", help="Path to screenshot image")
    ap.add_argument("--live", action="store_true", help="Take fresh screenshot via vnc-control.py")
    ap.add_argument("--query", default="Allow button", help="Element description to locate")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Model id (default: {DEFAULT_MODEL})")
    ap.add_argument("--out", default=None, help="Optional output JSON file")
    args = ap.parse_args()

    if args.live:
        screenshot_path = "/tmp/vnc-florence2-eval.jpg"
        if not take_vnc_screenshot(screenshot_path):
            raise SystemExit(1)
    elif args.screenshot:
        screenshot_path = args.screenshot
    else:
        ap.error("Provide --screenshot PATH or --live")

    result = run_detection(args.model, screenshot_path, args.query)
    payload = json.dumps(result, indent=2)
    print(payload)

    if args.out:
        Path(args.out).write_text(payload + "\n")


if __name__ == "__main__":
    main()
