#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_ID="${1:-matrix-$(date +%Y%m%d)-four-models}"
FIXTURE="${2:-bench/results/matrix-20260405/fixture.json}"
OUT_DIR="bench/results/${RUN_ID}"
PYTHON_BIN="${PYTHON_BIN:-/Users/openclaw/.openclaw/workspace/.venvs/vision-stack/bin/python}"

mkdir -p "$OUT_DIR"

"$PYTHON_BIN" bench/run_benchmark_matrix.py \
  --fixture "$FIXTURE" \
  --backends moondream,falcon,florence2,sam31 \
  --max-positive 8 \
  --max-negative 2 \
  --out-dir "$OUT_DIR"

echo "Wrote benchmark artifacts to: $OUT_DIR"
