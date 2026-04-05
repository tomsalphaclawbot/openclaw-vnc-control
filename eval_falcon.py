#!/usr/bin/env python3
"""
Benchmark Falcon Perception against existing VNC detection backends.

Primary use:
  python3 eval_falcon.py --screenshot /tmp/screen.jpg \
    --queries "Allow button" "Cancel" \
    --backends moondream falcon --reference-backend moondream --runs 2

This script is intentionally lightweight:
- Reuses detect_element() from vnc-control.py (same normalization path as production)
- Reports latency + localization proxy metrics
- Localization proxy = IoU + center distance versus a reference backend
"""

import argparse
import importlib.util
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent
VNC_CONTROL_PATH = ROOT / "vnc-control.py"


def load_vnc_module():
    spec = importlib.util.spec_from_file_location("vnc_control_eval", VNC_CONTROL_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def bbox_iou(a: dict, b: dict) -> Optional[float]:
    if not a or not b:
        return None
    ax1, ay1, ax2, ay2 = a["x_min"], a["y_min"], a["x_max"], a["y_max"]
    bx1, by1, bx2, by2 = b["x_min"], b["y_min"], b["x_max"], b["y_max"]

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih

    area_a = max(0.0, (ax2 - ax1)) * max(0.0, (ay2 - ay1))
    area_b = max(0.0, (bx2 - bx1)) * max(0.0, (by2 - by1))
    denom = area_a + area_b - inter
    if denom <= 0:
        return None
    return inter / denom


def center_distance(a: dict, b: dict) -> Optional[float]:
    if not a or not b:
        return None
    dx = float(a["x"]) - float(b["x"])
    dy = float(a["y"]) - float(b["y"])
    return (dx * dx + dy * dy) ** 0.5


def take_vnc_screenshot(out_path: str) -> Tuple[bool, str]:
    env = os.environ.copy()
    env.setdefault("VNC_HOST", "127.0.0.1")
    env.setdefault("VNC_PORT", "5900")
    env.setdefault("VNC_USERNAME", "openclaw")

    cmd = [
        sys.executable,
        str(VNC_CONTROL_PATH),
        "screenshot",
        "--format",
        "jpeg",
        "--scale",
        "0.5",
        "--out",
        out_path,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if p.returncode != 0:
        return False, p.stderr.strip() or p.stdout.strip()
    return True, ""


def summarize(entries: List[dict], reference_backend: str) -> Dict[str, dict]:
    by_backend: Dict[str, List[dict]] = {}
    for e in entries:
        by_backend.setdefault(e["backend"], []).append(e)

    # Index reference results by (run, query)
    ref_idx = {}
    for e in entries:
        if e["backend"] == reference_backend:
            ref_idx[(e["run"], e["query"])] = e

    summary = {}
    for backend, rows in by_backend.items():
        latencies = [r["elapsed_s"] for r in rows if r.get("elapsed_s") is not None]
        found = [r for r in rows if r.get("found")]

        ious = []
        dists = []
        for r in rows:
            ref = ref_idx.get((r["run"], r["query"]))
            if not ref or not ref.get("found") or not r.get("found"):
                continue
            iou = bbox_iou(r.get("box"), ref.get("box"))
            dist = center_distance(r.get("center"), ref.get("center"))
            if iou is not None:
                ious.append(iou)
            if dist is not None:
                dists.append(dist)

        summary[backend] = {
            "samples": len(rows),
            "found": len(found),
            "found_rate": (len(found) / len(rows)) if rows else 0.0,
            "latency_avg_s": statistics.mean(latencies) if latencies else None,
            "latency_median_s": statistics.median(latencies) if latencies else None,
            "iou_vs_ref_avg": statistics.mean(ious) if ious else None,
            "center_delta_vs_ref_px_avg": statistics.mean(dists) if dists else None,
            "reference_backend": reference_backend,
        }
    return summary


def main():
    p = argparse.ArgumentParser(description="Benchmark Falcon backend vs other VNC vision backends")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--screenshot", help="Path to screenshot image")
    src.add_argument("--live", action="store_true", help="Capture a fresh VNC screenshot")
    p.add_argument("--queries", nargs="+", required=True, help="One or more element queries")
    p.add_argument("--backends", nargs="+", default=["moondream", "falcon"],
                   help="Backends to benchmark (default: moondream falcon)")
    p.add_argument("--reference-backend", default="moondream",
                   help="Backend used as localization proxy reference (default: moondream)")
    p.add_argument("--runs", type=int, default=1, help="Number of repeated runs per query/backend")
    p.add_argument("--warmup", action="store_true", help="Run one warmup detect call per backend")
    p.add_argument("--out", help="Write JSON report to path")
    args = p.parse_args()

    if args.live:
        screenshot_path = "/tmp/vnc-falcon-bench.jpg"
        ok, err = take_vnc_screenshot(screenshot_path)
        if not ok:
            print(f"ERROR: screenshot capture failed: {err}", file=sys.stderr)
            sys.exit(1)
    else:
        screenshot_path = args.screenshot

    if not Path(screenshot_path).exists():
        print(f"ERROR: screenshot not found: {screenshot_path}", file=sys.stderr)
        sys.exit(1)

    vnc = load_vnc_module()

    if args.reference_backend not in args.backends:
        print(f"ERROR: --reference-backend '{args.reference_backend}' must be included in --backends", file=sys.stderr)
        sys.exit(2)

    entries: List[dict] = []

    if args.warmup:
        for backend in args.backends:
            try:
                _ = vnc.detect_element(screenshot_path, args.queries[0], backend=backend)
            except Exception:
                pass

    for run_idx in range(1, args.runs + 1):
        for query in args.queries:
            for backend in args.backends:
                t0 = time.time()
                try:
                    result = vnc.detect_element(screenshot_path, query, backend=backend)
                    elapsed_wall = time.time() - t0
                    entries.append({
                        "run": run_idx,
                        "query": query,
                        "backend": result.get("backend", backend),
                        "requested_backend": backend,
                        "found": bool(result.get("found")),
                        "elapsed_s": result.get("elapsed_s", elapsed_wall),
                        "elapsed_wall_s": round(elapsed_wall, 3),
                        "center": result.get("center"),
                        "box": result.get("box"),
                        "confidence": result.get("confidence"),
                        "error": result.get("error"),
                        "note": result.get("note"),
                    })
                except Exception as e:
                    entries.append({
                        "run": run_idx,
                        "query": query,
                        "backend": backend,
                        "requested_backend": backend,
                        "found": False,
                        "elapsed_s": None,
                        "elapsed_wall_s": round(time.time() - t0, 3),
                        "center": None,
                        "box": None,
                        "confidence": None,
                        "error": str(e),
                        "note": "exception",
                    })

    summary = summarize(entries, reference_backend=args.reference_backend)

    # Human-readable report
    print("\n=== Falcon Benchmark Report ===")
    print(f"screenshot: {screenshot_path}")
    print(f"queries: {args.queries}")
    print(f"runs: {args.runs}")
    print(f"reference backend: {args.reference_backend}")
    print("")
    print("backend      found_rate  avg_latency_s  median_latency_s  avg_iou_vs_ref  avg_center_delta_px")
    print("-----------  ----------  -------------  ----------------  --------------  -------------------")
    for backend in args.backends:
        s = summary.get(backend, {})
        def fmt(v, digits=3):
            return "-" if v is None else f"{v:.{digits}f}"
        print(
            f"{backend:<11}  "
            f"{fmt(s.get('found_rate')):<10}  "
            f"{fmt(s.get('latency_avg_s')):<13}  "
            f"{fmt(s.get('latency_median_s')):<16}  "
            f"{fmt(s.get('iou_vs_ref_avg')):<14}  "
            f"{fmt(s.get('center_delta_vs_ref_px_avg'), 2):<19}"
        )

    report = {
        "screenshot": screenshot_path,
        "queries": args.queries,
        "backends": args.backends,
        "reference_backend": args.reference_backend,
        "runs": args.runs,
        "summary": summary,
        "entries": entries,
    }

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"\nSaved JSON report to {args.out}")

    print("\n--- JSON SUMMARY ---")
    print(json.dumps({"summary": summary}, indent=2))


if __name__ == "__main__":
    main()
