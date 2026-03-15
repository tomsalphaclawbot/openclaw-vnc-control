#!/usr/bin/env python3
"""
VNC Click Accuracy regression runner for the VNC Click Lab.

This script clicks every deterministic button in the lab and verifies that the
backend log recorded the expected `button_click` label.

Expected lab layout:
- 22 labels
- deterministic 6x4 slot grid (first 22 slots used)
- section-relative x/y percentages from page.tsx

Notes:
- The script uses capture-space coordinates.
- Section geometry defaults are calibrated for the known local setup and can be
  overridden via CLI flags.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

# Probe offsets (capture space) to recover from slight coordinate drift.
OFFSETS: List[Tuple[int, int]] = [
    (0, 0),
    (6, 0),
    (-6, 0),
    (0, 6),
    (0, -6),
    (10, 10),
    (-10, 10),
    (10, -10),
    (-10, -10),
    (14, 0),
    (-14, 0),
    (0, 14),
    (0, -14),
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


def button_targets(section_left: int, section_top: int, section_w: int, section_h: int) -> List[Dict[str, object]]:
    slots = slot_percentages()
    targets: List[Dict[str, object]] = []
    for idx, label in enumerate(LABELS):
        x_pct, y_pct = slots[idx]
        x = int(round(section_left + section_w * (x_pct / 100.0)))
        y = int(round(section_top + section_h * (y_pct / 100.0)))
        targets.append(
            {
                "label": label,
                "x_pct": x_pct,
                "y_pct": y_pct,
                "x": x,
                "y": y,
            }
        )
    return targets


def run_vnc_click(vnc_binary: str, cwd: Path, x: int, y: int) -> Tuple[int, Dict[str, object]]:
    proc = subprocess.run(
        [vnc_binary, "click", str(x), str(y), "--space", "capture"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or proc.stderr or "").strip()
    parsed: Dict[str, object]
    try:
        parsed = json.loads(out) if out else {}
    except json.JSONDecodeError:
        parsed = {"raw": out}
    return proc.returncode, parsed


def read_new_events(log_path: Path, offset: int) -> Tuple[List[Dict[str, object]], int]:
    if not log_path.exists():
        return [], offset

    text = log_path.read_text(encoding="utf-8", errors="ignore")
    data = text.encode("utf-8")
    if offset >= len(data):
        return [], offset

    chunk_bytes = data[offset:]
    chunk = chunk_bytes.decode("utf-8", errors="ignore")
    events: List[Dict[str, object]] = []
    for line in chunk.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return events, len(data)


def latest_lab_event(events: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
    for ev in reversed(events):
        if ev.get("page") == "/vnc-click-lab":
            return ev
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Run full VNC Click Lab button regression")
    ap.add_argument("--log-path", required=True, help="Path to vnc-click-events.jsonl")
    ap.add_argument("--vnc-binary", default="./vnc", help="VNC wrapper binary (default: ./vnc)")
    ap.add_argument("--vnc-cwd", default=".", help="Working dir where vnc binary is resolved")
    ap.add_argument("--sleep", type=float, default=0.16, help="Delay after each click attempt")

    ap.add_argument("--section-left", type=int, default=16)
    ap.add_argument("--section-top", type=int, default=254)
    ap.add_argument("--section-width", type=int, default=1678)
    ap.add_argument("--section-height", type=int, default=712)

    ap.add_argument("--max-offsets", type=int, default=len(OFFSETS), help="Max jitter offsets to try per button")

    args = ap.parse_args()

    log_path = Path(args.log_path)
    vnc_cwd = Path(args.vnc_cwd).resolve()

    offset = 0
    if log_path.exists():
        offset = len(log_path.read_bytes())

    targets = button_targets(args.section_left, args.section_top, args.section_width, args.section_height)
    offsets = OFFSETS[: max(1, min(args.max_offsets, len(OFFSETS)))]

    results: List[Dict[str, object]] = []

    for t in targets:
        label = str(t["label"])
        x = int(t["x"])
        y = int(t["y"])

        ok = False
        last_detail: Dict[str, object] = {}
        attempts = 0

        for dx, dy in offsets:
            attempts += 1
            rc, click_out = run_vnc_click(args.vnc_binary, vnc_cwd, x + dx, y + dy)
            time.sleep(args.sleep)

            events, offset = read_new_events(log_path, offset)
            ev = latest_lab_event(events)

            detail: Dict[str, object] = {
                "offset": [dx, dy],
                "rc": rc,
                "click_out": click_out,
            }
            if ev:
                detail.update(
                    {
                        "event": ev.get("event"),
                        "event_label": ev.get("label"),
                        "clickX": ev.get("clickX"),
                        "clickY": ev.get("clickY"),
                        "requestId": ev.get("requestId"),
                    }
                )
            else:
                detail["event"] = None

            last_detail = detail

            if ev and ev.get("event") == "button_click" and ev.get("label") == label:
                ok = True
                break

        results.append(
            {
                "label": label,
                "target": {
                    "x_pct": t["x_pct"],
                    "y_pct": t["y_pct"],
                    "x": x,
                    "y": y,
                },
                "ok": ok,
                "attempts": attempts,
                "last": last_detail,
            }
        )

    ok_count = sum(1 for r in results if r["ok"])
    total = len(results)
    fails = [r for r in results if not r["ok"]]

    summary = {
        "ok_count": ok_count,
        "total": total,
        "pass_rate": round((ok_count / total) * 100, 2) if total else 0,
        "failed_labels": [f["label"] for f in fails],
        "results": results,
    }

    print(json.dumps(summary, indent=2))
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
