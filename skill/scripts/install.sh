#!/bin/bash
# Install vnc-control skill dependencies.
# Run from skill/scripts/ or any directory — resolves paths automatically.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_DIR"

# Create venv if missing
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q vncdotool Pillow

echo '{"ok": true, "action": "install", "venv": "'"$PROJECT_DIR/.venv"'", "tool": "'"$PROJECT_DIR/vnc-control.py"'"}'
