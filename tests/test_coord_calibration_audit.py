import json
import subprocess
import sys
from pathlib import Path


_ROOT = Path(__file__).parent.parent
_SCRIPT = _ROOT / "scripts" / "coord-calibration-audit.py"


def test_coord_calibration_audit_runs(tmp_path):
    out_json = tmp_path / "audit.json"
    cmd = [
        sys.executable,
        str(_SCRIPT),
        "--native-width",
        "320",
        "--native-height",
        "200",
        "--scale",
        "0.5",
        "--cols",
        "4",
        "--rows",
        "3",
        "--marker-radius",
        "5",
        "--out",
        str(out_json),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["audit"] == "synthetic-coordinate-roundtrip"
    assert payload["summary"]["samples"] == 12
    assert "median_error_native_px" in payload["summary"]
    assert out_json.exists()


def test_coord_calibration_audit_image_dump(tmp_path):
    img_dir = tmp_path / "imgs"
    cmd = [
        sys.executable,
        str(_SCRIPT),
        "--native-width",
        "180",
        "--native-height",
        "120",
        "--scale",
        "0.5",
        "--cols",
        "3",
        "--rows",
        "2",
        "--save-images-dir",
        str(img_dir),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout)
    artifacts = payload.get("artifacts", {})
    assert Path(artifacts["native_image"]).exists()
    assert Path(artifacts["screenshot_image"]).exists()
