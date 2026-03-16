#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Run all VNC Click Lab regressions (button clicks + input/keys).

Usage:
  scripts/run-all-regressions.sh [--log-path /path/to/logs/vnc-click-events.jsonl] [--vnc-cwd /path/to/openclaw-vnc-control]

Options:
  --log-path   Optional. Defaults to <vnc-cwd>/labs/vnc-click-lab/logs/vnc-click-events.jsonl
  --vnc-cwd    Optional. Defaults to current project root.
EOF
}

LOG_PATH=""
VNC_CWD="$(cd "$(dirname "$0")/.." && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --log-path)
      LOG_PATH="${2:-}"
      shift 2
      ;;
    --vnc-cwd)
      VNC_CWD="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$LOG_PATH" ]]; then
  LOG_PATH="$VNC_CWD/labs/vnc-click-lab/logs/vnc-click-events.jsonl"
fi

if [[ ! -f "$LOG_PATH" ]]; then
  echo "Error: log file not found: $LOG_PATH" >&2
  echo "Hint: run the standalone lab first (cd labs/vnc-click-lab && npm run dev), then generate events." >&2
  exit 1
fi

echo "[1/2] Running click regression..."
python3 "$VNC_CWD/scripts/click-regression.py" \
  --vnc-cwd "$VNC_CWD" \
  --log-path "$LOG_PATH"

echo "[2/2] Running input/key regression..."
python3 "$VNC_CWD/scripts/input-key-regression.py" \
  --vnc-cwd "$VNC_CWD" \
  --log-path "$LOG_PATH"

echo "✅ All regressions passed."
