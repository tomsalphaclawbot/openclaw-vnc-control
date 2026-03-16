#!/usr/bin/env python3
"""
VNC Click Lab calibration runner.

Purpose:
- Click deterministic targets in /vnc-click-lab
- Read server-side logs with page/client/screen telemetry
- Build a request(native) -> actual(native) correction map

Output:
- JSON summary to stdout
- Optional calibration JSON file for later use by tooling
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

LABELS: List[str] = [
    "QUIET LASER",
    "MANGO CIRCUIT",
    "NOVA PAPER",
    "RUSTY COMET",
    "VELVET SPARK",
    "TANGO FROST",
    "ATLAS PLUM",
    "PIXEL THUNDER",
    "VIOLET ANCHOR",
    "SILVER JUNGLE",
    "BRISK CANYON",
    "MAGNET OCEAN",
    "RAPID SAND",
    "EMBER BLOOM",
    "MIDNIGHT BANJO",
    "TINY SATURN",
    "PLASMA KOALA",
    "COPPER WAVE",
    "NEON PEBBLE",
    "GHOST PEPPER",
    "CRISP ROCKET",
    "MARBLE PULSE",
]

# Tiny jitter retries around each target.
OFFSETS: List[Tuple[int, int]] = [
    (0, 0),
    (4, 0),
    (-4, 0),
    (0, 4),
    (0, -4),
    (8, 8),
    (-8, 8),
    (8, -8),
    (-8, -8),
]


def slot_percentages() -> List[Tuple[float, float]]:
    cols, rows = 6, 4
    start_x, end_x = 40, 90
    start_y, end_y = 22, 88

    x_step = (end_x - start_x) / (cols - 1)
    y_step = (end_y - start_y) / (rows - 1)

    slots: List[Tuple[float, float]] = []
    for r in range(rows):
        for c in range(cols):
            slots.append((round(start_x + c * x_step, 2), round(start_y + r * y_step, 2)))
    return slots


def button_targets(section_left: int, section_top: int, section_w: int, section_h: int) -> List[Dict[str, Any]]:
    slots = slot_percentages()
    targets: List[Dict[str, Any]] = []

    for idx, label in enumerate(LABELS):
        x_pct, y_pct = slots[idx]
        x_capture = int(round(section_left + section_w * (x_pct / 100.0)))
        y_capture = int(round(section_top + section_h * (y_pct / 100.0)))
        targets.append(
            {
                "label": label,
                "x_pct": x_pct,
                "y_pct": y_pct,
                "x_capture": x_capture,
                "y_capture": y_capture,
            }
        )

    return targets


def run_click(vnc_binary: str, cwd: Path, x: int, y: int, space: str) -> Tuple[int, Dict[str, Any]]:
    proc = subprocess.run(
        [vnc_binary, "click", str(x), str(y), "--space", space],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )

    raw = (proc.stdout or proc.stderr or "").strip()
    payload: Dict[str, Any]
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {"raw": raw}

    return proc.returncode, payload


def read_events_since(log_path: Path, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    if not log_path.exists():
        return [], offset

    data = log_path.read_bytes()
    if offset >= len(data):
        return [], offset

    chunk = data[offset:].decode("utf-8", errors="ignore")
    events: List[Dict[str, Any]] = []

    for line in chunk.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return events, len(data)


def latest_click_event(events: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for ev in reversed(events):
        if ev.get("page") != "/vnc-click-lab":
            continue
        if ev.get("event") not in ("button_click", "background_click"):
            continue
        return ev
    return None


def get_nested(obj: Dict[str, Any], path: Sequence[str]) -> Optional[float]:
    cur: Any = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    if isinstance(cur, (int, float)):
        return float(cur)
    return None


def extract_actual_native(ev: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    x = get_nested(ev, ["pointerMeta", "derivedFromPage", "screenNativeX"])
    y = get_nested(ev, ["pointerMeta", "derivedFromPage", "screenNativeY"])
    if x is not None and y is not None:
        return x, y

    x2 = get_nested(ev, ["pointerMeta", "eventScreenNativeX"])
    y2 = get_nested(ev, ["pointerMeta", "eventScreenNativeY"])
    return x2, y2


def extract_requested_native(click_out: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    x = get_nested(click_out, ["native_coords", "x"])
    y = get_nested(click_out, ["native_coords", "y"])
    return x, y


def solve_3x3(mat: List[List[float]], vec: List[float]) -> Optional[List[float]]:
    # Gaussian elimination with partial pivoting.
    a = [row[:] + [vec[i]] for i, row in enumerate(mat)]
    n = 3

    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot_row][col]) < 1e-9:
            return None
        if pivot_row != col:
            a[col], a[pivot_row] = a[pivot_row], a[col]

        pivot = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= pivot

        for r in range(n):
            if r == col:
                continue
            factor = a[r][col]
            for j in range(col, n + 1):
                a[r][j] -= factor * a[col][j]

    return [a[i][n] for i in range(n)]


def fit_affine(points: Sequence[Tuple[float, float, float, float]]) -> Optional[Dict[str, Any]]:
    # points: (req_x, req_y, actual_x, actual_y)
    if len(points) < 3:
        return None

    # Build normal equations for [a,b,c] where out = a*x + b*y + c
    def normal_solve(target_index: int) -> Optional[List[float]]:
        # target_index: 2 => actual_x, 3 => actual_y
        ata = [[0.0, 0.0, 0.0] for _ in range(3)]
        atb = [0.0, 0.0, 0.0]

        for p in points:
            x, y = p[0], p[1]
            t = p[target_index]
            row = [x, y, 1.0]
            for i in range(3):
                for j in range(3):
                    ata[i][j] += row[i] * row[j]
                atb[i] += row[i] * t

        return solve_3x3(ata, atb)

    px = normal_solve(2)
    py = normal_solve(3)
    if px is None or py is None:
        return None

    def apply(req_x: float, req_y: float) -> Tuple[float, float]:
        return (
            px[0] * req_x + px[1] * req_y + px[2],
            py[0] * req_x + py[1] * req_y + py[2],
        )

    errs: List[float] = []
    dxs: List[float] = []
    dys: List[float] = []

    for req_x, req_y, act_x, act_y in points:
        pred_x, pred_y = apply(req_x, req_y)
        errs.append(math.hypot(pred_x - act_x, pred_y - act_y))
        dxs.append(act_x - req_x)
        dys.append(act_y - req_y)

    rmse = math.sqrt(sum(e * e for e in errs) / len(errs)) if errs else None

    return {
        "x_params": {"a": px[0], "b": px[1], "c": px[2]},
        "y_params": {"d": py[0], "e": py[1], "f": py[2]},
        "samples": len(points),
        "rmse_native_px": rmse,
        "mean_raw_delta_native": {
            "dx": sum(dxs) / len(dxs) if dxs else None,
            "dy": sum(dys) / len(dys) if dys else None,
        },
        "max_fit_error_native_px": max(errs) if errs else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Calibrate VNC click mapping from click lab telemetry")
    ap.add_argument("--log-path", required=True, help="Path to vnc-click-events.jsonl")
    ap.add_argument("--vnc-cwd", required=True, help="Directory containing ./vnc wrapper")
    ap.add_argument("--vnc-binary", default="./vnc", help="VNC binary/wrapper")
    ap.add_argument("--space", choices=["capture", "native", "screenshot"], default="capture")
    ap.add_argument("--sleep", type=float, default=0.2)

    ap.add_argument("--section-left", type=int, default=16)
    ap.add_argument("--section-top", type=int, default=254)
    ap.add_argument("--section-width", type=int, default=1678)
    ap.add_argument("--section-height", type=int, default=712)

    ap.add_argument("--max-offsets", type=int, default=3, help="Retries with tiny jitter per target")
    ap.add_argument(
        "--out",
        default="state/click-calibration.json",
        help="Calibration output JSON path (relative to --vnc-cwd if not absolute)",
    )

    args = ap.parse_args()

    log_path = Path(args.log_path)
    vnc_cwd = Path(args.vnc_cwd).resolve()

    offset = len(log_path.read_bytes()) if log_path.exists() else 0
    targets = button_targets(args.section_left, args.section_top, args.section_width, args.section_height)
    offsets = OFFSETS[: max(1, min(args.max_offsets, len(OFFSETS)))]

    samples: List[Dict[str, Any]] = []
    fit_points: List[Tuple[float, float, float, float]] = []

    for t in targets:
        label = str(t["label"])
        base_x = int(t["x_capture"])
        base_y = int(t["y_capture"])

        hit: Optional[Dict[str, Any]] = None

        for dx, dy in offsets:
            req_x = base_x + dx
            req_y = base_y + dy

            rc, click_out = run_click(args.vnc_binary, vnc_cwd, req_x, req_y, args.space)
            time.sleep(args.sleep)

            events, offset = read_events_since(log_path, offset)
            ev = latest_click_event(events)

            requested_native_x, requested_native_y = extract_requested_native(click_out)
            actual_native_x, actual_native_y = (None, None)
            if ev:
                actual_native_x, actual_native_y = extract_actual_native(ev)

            row = {
                "label": label,
                "requested": {
                    "space": args.space,
                    "x": req_x,
                    "y": req_y,
                    "native_x": requested_native_x,
                    "native_y": requested_native_y,
                },
                "click_rc": rc,
                "event": ev,
                "actual_native": {
                    "x": actual_native_x,
                    "y": actual_native_y,
                },
            }

            is_label_match = bool(ev and ev.get("event") == "button_click" and ev.get("label") == label)
            has_native = requested_native_x is not None and requested_native_y is not None and actual_native_x is not None and actual_native_y is not None

            if is_label_match:
                hit = row
                if has_native:
                    fit_points.append((requested_native_x, requested_native_y, actual_native_x, actual_native_y))
                break

            # Keep last attempt as fallback evidence
            hit = row

        if hit is None:
            hit = {
                "label": label,
                "requested": {"space": args.space, "x": base_x, "y": base_y},
                "click_rc": 999,
                "event": None,
                "actual_native": {"x": None, "y": None},
                "error": "no attempts executed",
            }

        samples.append(hit)

    affine = fit_affine(fit_points)

    output: Dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "vnc_cwd": str(vnc_cwd),
        "log_path": str(log_path),
        "space": args.space,
        "targets": len(targets),
        "fit_samples": len(fit_points),
        "affine_native": affine,
        "samples": samples,
    }

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = vnc_cwd / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(json.dumps({
        "ok": affine is not None,
        "fit_samples": len(fit_points),
        "targets": len(targets),
        "calibration_out": str(out_path),
        "affine_native": affine,
    }, indent=2))

    return 0 if affine is not None else 2


if __name__ == "__main__":
    sys.exit(main())
