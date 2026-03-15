#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /path/to/nextjs-app" >&2
  exit 1
fi

TARGET="$1"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$TARGET/app/vnc-click-lab" "$TARGET/app/api/vnc-click-log"
cp "$SRC_DIR/app/vnc-click-lab/page.tsx" "$TARGET/app/vnc-click-lab/page.tsx"
cp "$SRC_DIR/app/api/vnc-click-log/route.ts" "$TARGET/app/api/vnc-click-log/route.ts"

echo "Installed VNC Click Lab into: $TARGET"
echo "Open: http://localhost:<port>/vnc-click-lab"
