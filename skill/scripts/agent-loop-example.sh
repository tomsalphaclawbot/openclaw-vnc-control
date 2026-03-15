#!/bin/bash
# Example: single observe→act cycle using vnc-control.
# This script demonstrates the pattern an AI agent would use.
# In practice, the AI model replaces the hardcoded coordinates below.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
TOOL="$PROJECT_DIR/.venv/bin/python3 $PROJECT_DIR/vnc-control.py"

# Ensure venv exists
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "Run install.sh first"
    exit 1
fi

WORKDIR="${1:-/tmp/vnc-agent-loop}"
mkdir -p "$WORKDIR"

echo "=== 1. Status check ==="
$TOOL status

echo ""
echo "=== 2. Screenshot (JPEG 50%) ==="
$TOOL screenshot --format jpeg --scale 0.5 --out "$WORKDIR/observe.jpg"

echo ""
echo "=== Feed observe.jpg to your vision model here ==="
echo "=== Model returns: {\"action\": \"click\", \"x\": 500, \"y\": 300} ==="
echo ""

# In a real agent loop, parse the model's response for coordinates.
# This is just a demonstration placeholder:
# echo "=== 3. Act ==="
# $TOOL click 500 300
#
# echo ""
# echo "=== 4. Verify ==="
# $TOOL screenshot --format jpeg --scale 0.5 --out "$WORKDIR/verify.jpg"

echo "Done. Screenshot saved to $WORKDIR/observe.jpg"
echo "An AI agent would now analyze the image, determine action, execute, and verify."
