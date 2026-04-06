#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAB_DIR="$ROOT_DIR/labs/vnc-click-lab"
LOG_DIR="$ROOT_DIR/bench/results"
PORT="${PORT:-3015}"
PID_FILE="$LOG_DIR/click-lab-dev.pid"
LOG_FILE="$LOG_DIR/click-lab-dev.log"
OPEN_BROWSER="${OPEN_BROWSER:-0}"
TIMEOUT_S="${TIMEOUT_S:-60}"

mkdir -p "$LOG_DIR"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required but not found" >&2
  exit 1
fi

if [[ ! -d "$LAB_DIR" ]]; then
  echo "Lab directory not found: $LAB_DIR" >&2
  exit 1
fi

# Reuse running process when port is already listening.
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "click-lab already listening on :$PORT"
else
  if [[ ! -d "$LAB_DIR/node_modules" ]]; then
    echo "Installing lab dependencies (npm install)..."
    (cd "$LAB_DIR" && npm install)
  fi

  echo "Starting click-lab dev server on :$PORT"
  (
    cd "$LAB_DIR"
    nohup npx next dev -p "$PORT" >"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
  )
fi

echo "Waiting for http://127.0.0.1:$PORT/vnc-click-lab ..."
start_ts="$(date +%s)"
while true; do
  if curl -fsS "http://127.0.0.1:$PORT/vnc-click-lab" >/dev/null 2>&1; then
    break
  fi
  now_ts="$(date +%s)"
  if (( now_ts - start_ts > TIMEOUT_S )); then
    echo "Timed out waiting for click-lab on port $PORT" >&2
    echo "Tail of log:" >&2
    tail -n 80 "$LOG_FILE" >&2 || true
    exit 1
  fi
  sleep 1
done

if [[ "$OPEN_BROWSER" == "1" ]] && command -v open >/dev/null 2>&1; then
  open "http://127.0.0.1:$PORT/vnc-click-lab" || true
fi

cat <<EOF
{
  "ok": true,
  "port": $PORT,
  "url": "http://127.0.0.1:$PORT/vnc-click-lab",
  "log": "$LOG_FILE",
  "pid_file": "$PID_FILE"
}
EOF
