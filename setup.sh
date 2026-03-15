#!/bin/bash
# Setup vnc-control development environment
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Setting up vnc-control..."

# Create venv if missing
if [ ! -d ".venv" ]; then
    echo "Creating Python venv..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q vncdotool Pillow

echo ""
echo "Done. Usage:"
echo "  source .venv/bin/activate"
echo "  python3 vnc-control.py status"
echo "  python3 vnc-control.py screenshot --out screen.png"
echo "  python3 vnc-control.py click 100 200"
echo "  python3 vnc-control.py type 'hello'"
echo ""
echo "Connection config via env:"
echo "  export VNC_HOST=127.0.0.1"
echo "  export VNC_PORT=5900"
echo "  export VNC_PASSWORD=yourpass"
echo "  export VNC_USERNAME=youruser  # for macOS ARD auth"
