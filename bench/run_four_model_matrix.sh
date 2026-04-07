#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_ID="${1:-matrix-$(date +%Y%m%d)-four-models}"
FIXTURE="${2:-bench/results/matrix-20260405/fixture.json}"
OUT_DIR="bench/results/${RUN_ID}"
PYTHON_BIN="${PYTHON_BIN:-/Users/openclaw/.openclaw/workspace/.venvs/vision-stack/bin/python}"
SYSTEM_PYTHON="${SYSTEM_PYTHON:-python3}"

mkdir -p "$OUT_DIR"

"$SYSTEM_PYTHON" - "$FIXTURE" "$OUT_DIR" "$RUN_ID" <<'PY'
import json
import shutil
from pathlib import Path
import sys

src_fixture = Path(sys.argv[1]).resolve()
out_dir = Path(sys.argv[2]).resolve()
run_id = sys.argv[3]

data = json.loads(src_fixture.read_text())
img_ref = (data.get("image") or {}).get("path")
if not img_ref:
    raise SystemExit("Fixture missing image.path")

img_path = Path(img_ref)
if not img_path.is_absolute():
    img_path = (src_fixture.parent / img_path).resolve()
if not img_path.exists():
    fallback = (src_fixture.parent / Path(img_ref).name).resolve()
    if fallback.exists():
        img_path = fallback
    else:
        raise SystemExit(f"Fixture image not found: {img_path}")

dst_img = out_dir / "fixture-click-lab.png"
shutil.copy2(img_path, dst_img)

data["run_id"] = run_id
data["image"] = dict(data.get("image") or {})
data["image"]["path"] = str(dst_img)

dst_fixture = out_dir / "fixture.json"
dst_fixture.write_text(json.dumps(data, indent=2), encoding="utf-8")
print(dst_fixture)
PY

FIXTURE_IN_OUT="$OUT_DIR/fixture.json"

"$PYTHON_BIN" bench/run_benchmark_matrix.py \
  --fixture "$FIXTURE_IN_OUT" \
  --backends moondream,falcon,florence2,sam31 \
  --max-positive 8 \
  --max-negative 2 \
  --out-dir "$OUT_DIR"

echo "Wrote benchmark artifacts to: $OUT_DIR"
