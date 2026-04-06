#!/usr/bin/env python3
"""
Synthetic coordinate calibration audit.

Purpose:
- Validate screenshot-space -> native-space coordinate math with objective, repeatable data.
- Draw deterministic synthetic markers at known native coordinates.
- Downscale to screenshot-space (same shape as real capture flow).
- Re-detect marker centers in screenshot pixels.
- Round-trip detected screenshot coords back to native and measure error.

This is a no-VNC calibration sanity check that complements click-lab telemetry tests.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw

try:
    import numpy as np
except Exception:  # pragma: no cover - import guard for minimal environments
    np = None


def load_vnc_module(repo_root: Path):
    script = repo_root / "vnc-control.py"
    spec = importlib.util.spec_from_file_location("vnc_control", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load {script}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_points(native_w: int, native_h: int, cols: int, rows: int) -> List[Tuple[int, int]]:
    x0, x1 = int(native_w * 0.08), int(native_w * 0.92)
    y0, y1 = int(native_h * 0.12), int(native_h * 0.88)
    xs = np.linspace(x0, x1, cols)
    ys = np.linspace(y0, y1, rows)
    pts: List[Tuple[int, int]] = []
    for y in ys:
        for x in xs:
            pts.append((int(round(x)), int(round(y))))
    return pts


def marker_palette(n: int) -> List[Tuple[int, int, int]]:
    colors: List[Tuple[int, int, int]] = []
    for i in range(n):
        # Deterministic bright-ish palette (avoids black background and channel collapse)
        r = 40 + ((53 * i) % 200)
        g = 40 + ((97 * i) % 200)
        b = 40 + ((149 * i) % 200)
        colors.append((int(r), int(g), int(b)))
    return colors


def draw_markers(native_w: int, native_h: int, points: Sequence[Tuple[int, int]],
                 colors: Sequence[Tuple[int, int, int]], radius: int) -> Image.Image:
    img = Image.new("RGB", (native_w, native_h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for (x, y), c in zip(points, colors):
        d.ellipse((x - radius, y - radius, x + radius, y + radius), fill=c)
        d.line((x - radius - 1, y, x + radius + 1, y), fill=c, width=1)
        d.line((x, y - radius - 1, x, y + radius + 1), fill=c, width=1)
    return img


def detect_marker_center(arr: np.ndarray, color: Tuple[int, int, int], tolerance: int) -> Tuple[float, float, int]:
    target = np.array(color, dtype=np.int16)
    delta = np.abs(arr.astype(np.int16) - target).sum(axis=2)
    mask = delta <= tolerance

    if mask.any():
        ys, xs = np.where(mask)
        return float(xs.mean()), float(ys.mean()), int(mask.sum())

    # Fallback: best color-distance pixel if anti-aliasing washed out exact color.
    iy, ix = np.unravel_index(np.argmin(delta), delta.shape)
    return float(ix), float(iy), 1


def p95(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    arr = sorted(values)
    idx = min(len(arr) - 1, int(math.ceil(0.95 * len(arr)) - 1))
    return float(arr[idx])


def main() -> None:
    if np is None:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "numpy is required for coord-calibration-audit",
                    "install": "pip install numpy pillow",
                },
                indent=2,
            )
        )
        raise SystemExit(1)

    ap = argparse.ArgumentParser(description="Synthetic screenshot/native coordinate calibration audit")
    ap.add_argument("--native-width", type=int, default=3420)
    ap.add_argument("--native-height", type=int, default=2214)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--rows", type=int, default=4)
    ap.add_argument("--marker-radius", type=int, default=7)
    ap.add_argument("--tolerance", type=int, default=95,
                    help="Color-distance tolerance for marker re-detection in screenshot space")
    ap.add_argument("--resample", choices=["lanczos", "nearest"], default="lanczos")
    ap.add_argument("--max-error-pass", type=float, default=3.0,
                    help="Pass threshold for max native error (px)")
    ap.add_argument("--save-images-dir", default=None,
                    help="Optional directory to save synthetic native/screenshot images")
    ap.add_argument("--out", default=None, help="Optional JSON output path")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    vnc = load_vnc_module(repo_root)

    native_w = max(10, int(args.native_width))
    native_h = max(10, int(args.native_height))
    scale = float(args.scale)
    if not (0 < scale <= 1.0):
        raise SystemExit("--scale must be in (0, 1]")

    points = make_points(native_w, native_h, max(2, args.cols), max(2, args.rows))
    colors = marker_palette(len(points))

    native_img = draw_markers(native_w, native_h, points, colors, max(2, args.marker_radius))

    screenshot_w = max(1, int(native_w * scale))
    screenshot_h = max(1, int(native_h * scale))
    resample = Image.LANCZOS if args.resample == "lanczos" else Image.NEAREST
    screenshot_img = native_img.resize((screenshot_w, screenshot_h), resample)

    arr = np.array(screenshot_img, dtype=np.uint8)

    samples: List[Dict[str, object]] = []
    errors: List[float] = []

    for idx, ((native_x, native_y), color) in enumerate(zip(points, colors), start=1):
        sx_f, sy_f, pix_count = detect_marker_center(arr, color, max(0, args.tolerance))
        sx = int(round(sx_f))
        sy = int(round(sy_f))

        mapped_native_x, mapped_native_y = vnc.to_native(sx, sy, scale)
        expected_sx, expected_sy = vnc.from_native(native_x, native_y, scale)

        err = math.hypot(mapped_native_x - native_x, mapped_native_y - native_y)
        errors.append(err)

        samples.append(
            {
                "id": idx,
                "native_target": {"x": native_x, "y": native_y},
                "detected_screenshot": {"x": sx, "y": sy, "pixels": pix_count},
                "expected_screenshot": {"x": expected_sx, "y": expected_sy},
                "mapped_native": {"x": mapped_native_x, "y": mapped_native_y},
                "error_native_px": round(err, 4),
            }
        )

    median_err = float(np.median(np.array(errors))) if errors else 0.0
    max_err = float(max(errors)) if errors else 0.0
    mean_err = float(np.mean(np.array(errors))) if errors else 0.0

    result = {
        "ok": True,
        "audit": "synthetic-coordinate-roundtrip",
        "native": {"width": native_w, "height": native_h},
        "screenshot": {"width": screenshot_w, "height": screenshot_h},
        "scale": {
            "nominal": scale,
            "effective_x": round(screenshot_w / native_w, 8),
            "effective_y": round(screenshot_h / native_h, 8),
            "resample": args.resample,
        },
        "summary": {
            "samples": len(samples),
            "median_error_native_px": round(median_err, 4),
            "p95_error_native_px": round(p95(errors), 4),
            "mean_error_native_px": round(mean_err, 4),
            "max_error_native_px": round(max_err, 4),
            "pass_threshold_native_px": float(args.max_error_pass),
            "pass": bool(max_err <= float(args.max_error_pass)),
        },
        "samples": samples,
    }

    if args.save_images_dir:
        out_dir = Path(args.save_images_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        native_path = out_dir / "synthetic-native.png"
        screenshot_path = out_dir / "synthetic-screenshot.png"
        native_img.save(native_path)
        screenshot_img.save(screenshot_path)
        result["artifacts"] = {
            "native_image": str(native_path),
            "screenshot_image": str(screenshot_path),
        }

    payload = json.dumps(result, indent=2)
    print(payload)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n")


if __name__ == "__main__":
    main()
