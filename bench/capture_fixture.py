#!/usr/bin/env python3
"""Capture a deterministic click-lab fixture screenshot + ground truth coordinates.

Flow:
1) Uses Playwright CLI to open /vnc-click-lab and save a viewport screenshot.
2) Reads /api/element-coords (reported by useCoordReporter on page load).
3) Emits fixture JSON with per-element center coordinates in screenshot space.

This keeps fixture generation reproducible without requiring VNC credentials.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_json(url: str, timeout: float = 10.0) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (local URL)
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Capture click-lab benchmark fixture")
    p.add_argument("--base-url", default="http://127.0.0.1:3015", help="click-lab base URL")
    p.add_argument("--page", default="/vnc-click-lab", help="lab page path")
    p.add_argument("--viewport", default="1710,913", help='viewport as "W,H"')
    p.add_argument("--wait-ms", type=int, default=2000, help="wait before screenshot")
    p.add_argument("--out-dir", default="bench/results", help="output root directory")
    p.add_argument("--run-id", default=None, help="optional run id (directory name)")
    p.add_argument("--retries", type=int, default=6, help="coord snapshot fetch retries")
    p.add_argument("--retry-delay", type=float, default=0.8, help="seconds between retries")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    root = Path.cwd()

    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = root / args.out_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    image_path = out_dir / "fixture-click-lab.png"
    fixture_path = out_dir / "fixture.json"

    viewport = args.viewport.replace(" ", "")
    target_url = f"{args.base_url.rstrip('/')}{args.page}"

    screenshot_cmd = [
        "npx",
        "--yes",
        "playwright",
        "screenshot",
        "--browser",
        "chromium",
        "--viewport-size",
        viewport,
        "--wait-for-timeout",
        str(args.wait_ms),
        target_url,
        str(image_path),
    ]
    _run(screenshot_cmd)

    coords_url = f"{args.base_url.rstrip('/')}/api/element-coords"
    coords: dict[str, Any] | None = None
    last_err: Exception | None = None
    for _ in range(max(1, args.retries)):
        try:
            snapshot = _fetch_json(coords_url)
            if snapshot.get("ok"):
                coords = snapshot
                break
            last_err = RuntimeError(snapshot.get("error", "unknown /api/element-coords error"))
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(max(0.0, args.retry_delay))

    if coords is None:
        raise RuntimeError(f"Failed to fetch {coords_url}: {last_err}")

    with Image.open(image_path) as img:
        image_w, image_h = img.size

    elements = []
    for el in coords.get("elements", []):
        center = el.get("center") or {}
        cx = float(center.get("clientX", 0.0))
        cy = float(center.get("clientY", 0.0))
        elements.append(
            {
                "id": el.get("id"),
                "label": el.get("label"),
                "kind": el.get("kind"),
                "center_px": {"x": cx, "y": cy},
                "center_norm": {
                    "x": round(cx / image_w, 6) if image_w else 0.0,
                    "y": round(cy / image_h, 6) if image_h else 0.0,
                },
                "rect": el.get("rect") or {},
            }
        )

    elements.sort(key=lambda x: (str(x.get("kind")), str(x.get("id"))))

    fixture = {
        "generated_at": _utc_now(),
        "run_id": run_id,
        "source": {
            "base_url": args.base_url,
            "page": args.page,
            "coords_url": coords_url,
        },
        "image": {
            "path": str(image_path),
            "width": image_w,
            "height": image_h,
            "viewport": viewport,
        },
        "window_metrics": coords.get("windowMetrics", {}),
        "captured_at": coords.get("capturedAt"),
        "received_at": coords.get("receivedAt"),
        "elements": elements,
        "negative_queries": [
            {
                "id": "neg-no-such-grid-button",
                "query": 'button labeled "OBSIDIAN BANANA"',
                "expected_found": False,
            },
            {
                "id": "neg-no-such-icon-button",
                "query": 'icon button labeled "Teleport"',
                "expected_found": False,
            },
            {
                "id": "neg-no-such-input",
                "query": 'input field named "ghost_field"',
                "expected_found": False,
            },
        ],
    }

    fixture_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "run_id": run_id,
                "fixture": str(fixture_path),
                "image": str(image_path),
                "element_count": len(elements),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise
