#!/usr/bin/env python3
"""
Gemma 4 vision evaluation for VNC element detection.
Tests if the local Gemma 4 26B MoE server can extract bounding boxes from screenshots.

Requires: gemma4 server running on port 8890
  bash projects/gemma4-local/gemma4-server.sh

Usage:
    python3 eval_gemma4_vision.py --screenshot screen.jpg --query "Allow button"
    python3 eval_gemma4_vision.py --live --queries "Allow button" "Cancel button"
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path


GEMMA4_ENDPOINT = os.environ.get("GEMMA4_ENDPOINT", "http://127.0.0.1:8890")
DEFAULT_MODEL = "mlx-community/gemma-4-26b-a4b-it-4bit"

DETECTION_PROMPT = """\
Look at this screenshot of a macOS desktop. Your task is to locate a specific UI element.

Element to find: "{query}"

If the element is visible, return ONLY a JSON object with these fields:
{{
  "found": true,
  "x_min": <float 0-1>,
  "y_min": <float 0-1>,
  "x_max": <float 0-1>,
  "y_max": <float 0-1>,
  "confidence": "high" | "medium" | "low",
  "note": "<optional short note about what you found>"
}}

If the element is NOT visible, return ONLY:
{{
  "found": false,
  "note": "<why not found>"
}}

Do not include any other text. Return only the JSON object."""


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def detect_element(image_path: str, query: str, model: str = DEFAULT_MODEL) -> dict:
    """Call Gemma4 local server with image + query, parse bounding box from response."""
    import urllib.request

    img_b64 = encode_image(image_path)
    # Detect image format
    suffix = Path(image_path).suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"

    prompt = DETECTION_PROMPT.format(query=query)

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{img_b64}"}
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        "max_tokens": 200,
        "temperature": 0.0,
    }

    t0 = time.time()
    req = urllib.request.Request(
        f"{GEMMA4_ENDPOINT}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "vnc-eval/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
    except Exception as e:
        return {"found": False, "error": str(e), "elapsed_s": round(time.time() - t0, 2)}
    elapsed = time.time() - t0

    raw_text = body["choices"][0]["message"]["content"].strip()

    # Parse JSON from response (model may wrap in ```json ... ```)
    try:
        # Strip markdown fences if present
        text = raw_text
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text.strip())
    except json.JSONDecodeError:
        return {
            "found": False,
            "error": "JSON parse failed",
            "raw_response": raw_text,
            "elapsed_s": round(elapsed, 2),
        }

    result["elapsed_s"] = round(elapsed, 2)
    result["model"] = model
    result["query"] = query

    # If found, compute pixel coords from image dimensions
    if result.get("found"):
        from PIL import Image
        img = Image.open(image_path)
        w, h = img.size
        x_min = result["x_min"] * w
        y_min = result["y_min"] * h
        x_max = result["x_max"] * w
        y_max = result["y_max"] * h
        result["image_size"] = [w, h]
        result["box_px"] = {
            "x_min": round(x_min), "y_min": round(y_min),
            "x_max": round(x_max), "y_max": round(y_max),
        }
        result["center_px"] = {
            "x": round((x_min + x_max) / 2),
            "y": round((y_min + y_max) / 2),
        }

    return result


def take_vnc_screenshot(out_path: str) -> bool:
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
    return result.returncode == 0


def check_server() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"{GEMMA4_ENDPOINT}/v1/models", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Gemma 4 VNC vision element detection eval")
    parser.add_argument("--screenshot", help="Path to existing screenshot")
    parser.add_argument("--live", action="store_true", help="Take fresh VNC screenshot")
    parser.add_argument("--query", default="Allow button", help="Element to find")
    parser.add_argument("--queries", nargs="+", help="Multiple queries")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model to use")
    parser.add_argument("--out", help="Save results JSON here")
    args = parser.parse_args()

    if not check_server():
        print(f"ERROR: Gemma4 server not running at {GEMMA4_ENDPOINT}", file=sys.stderr)
        print("Start it: bash projects/gemma4-local/gemma4-server.sh", file=sys.stderr)
        sys.exit(1)
    print(f"Server: {GEMMA4_ENDPOINT} ✓")

    if args.live:
        screenshot_path = "/tmp/vnc-gemma4-eval.jpg"
        print(f"Taking VNC screenshot -> {screenshot_path}")
        if not take_vnc_screenshot(screenshot_path):
            sys.exit(1)
    elif args.screenshot:
        screenshot_path = args.screenshot
    else:
        parser.error("Provide --screenshot <path> or --live")

    queries = args.queries or [args.query]
    results = []
    for q in queries:
        print(f"\nQuery: '{q}'", flush=True)
        r = detect_element(screenshot_path, q, model=args.model)
        results.append(r)
        if r.get("found"):
            c = r["center_px"]
            b = r["box_px"]
            conf = r.get("confidence", "?")
            print(f"  FOUND [{conf}] center ({c['x']}, {c['y']}), "
                  f"box [{b['x_min']},{b['y_min']} → {b['x_max']},{b['y_max']}], "
                  f"{r['elapsed_s']}s")
            if r.get("note"):
                print(f"  Note: {r['note']}")
        else:
            err = r.get("error") or r.get("note") or "not visible"
            print(f"  NOT FOUND — {err} ({r['elapsed_s']}s)")
            if r.get("raw_response"):
                print(f"  Raw: {r['raw_response'][:200]}")

    output = {"screenshot": screenshot_path, "model": args.model, "results": results}
    print("\n--- JSON ---")
    print(json.dumps(output, indent=2))

    if args.out:
        Path(args.out).write_text(json.dumps(output, indent=2))
        print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    main()
