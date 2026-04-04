/**
 * /api/element-coords
 *
 * Source of truth for element screen coordinates.
 *
 * The page calls POST with a full snapshot of all button bounding rects
 * converted to native screen pixels (getBoundingClientRect + screenX/Y + devicePixelRatio).
 *
 * The benchmark runner calls GET to retrieve the latest snapshot —
 * exact native screen coordinates for every element, ready to feed into vnc-control.
 *
 * POST body:
 * {
 *   capturedAt: ISO timestamp (client),
 *   windowMetrics: { screenX, screenY, innerWidth, innerHeight, devicePixelRatio, scrollX, scrollY },
 *   elements: [
 *     {
 *       id: "btn-1",
 *       label: "ATLAS PLUM",
 *       kind: "button" | "input" | "select" | "icon-button",
 *       rect: { top, left, right, bottom, width, height },   // getBoundingClientRect(), CSS px
 *       center: { clientX, clientY },                        // CSS px, relative to viewport
 *       screen: { cssX, cssY, nativeX, nativeY },            // native screen pixels (what VNC needs)
 *     },
 *     ...
 *   ]
 * }
 *
 * GET response:
 * {
 *   ok: true,
 *   capturedAt: "...",
 *   receivedAt: "...",
 *   windowMetrics: { ... },
 *   elements: [ ... ],   // same shape as POST body elements
 * }
 */

import { NextRequest, NextResponse } from "next/server";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import path from "node:path";

const STATE_DIR = path.join(process.cwd(), "state");
const SNAPSHOT_PATH = path.join(STATE_DIR, "element-coords-snapshot.json");

type WindowMetrics = {
  screenX: number;
  screenY: number;
  innerWidth: number;
  innerHeight: number;
  devicePixelRatio: number;
  scrollX: number;
  scrollY: number;
};

type ElementRect = {
  top: number;
  left: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
};

type ElementCoord = {
  id: string;
  label: string;
  kind: string;
  rect: ElementRect;
  center: { clientX: number; clientY: number };
  screen: {
    cssX: number;
    cssY: number;
    nativeX: number;
    nativeY: number;
  };
};

type Snapshot = {
  capturedAt: string;
  receivedAt: string;
  windowMetrics: WindowMetrics;
  elements: ElementCoord[];
};

export async function POST(req: NextRequest) {
  let body: { capturedAt?: string; windowMetrics?: WindowMetrics; elements?: ElementCoord[] };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }

  if (!body.elements || !Array.isArray(body.elements) || body.elements.length === 0) {
    return NextResponse.json({ ok: false, error: "elements array required" }, { status: 400 });
  }
  if (!body.windowMetrics) {
    return NextResponse.json({ ok: false, error: "windowMetrics required" }, { status: 400 });
  }

  const snapshot: Snapshot = {
    capturedAt: body.capturedAt ?? new Date().toISOString(),
    receivedAt: new Date().toISOString(),
    windowMetrics: body.windowMetrics,
    elements: body.elements,
  };

  await mkdir(STATE_DIR, { recursive: true });
  await writeFile(SNAPSHOT_PATH, JSON.stringify(snapshot, null, 2), "utf8");

  return NextResponse.json({
    ok: true,
    receivedAt: snapshot.receivedAt,
    elementCount: snapshot.elements.length,
    elements: snapshot.elements.map((e) => ({
      id: e.id,
      label: e.label,
      nativeX: e.screen.nativeX,
      nativeY: e.screen.nativeY,
    })),
  });
}

export async function GET() {
  try {
    const text = await readFile(SNAPSHOT_PATH, "utf8");
    const snapshot: Snapshot = JSON.parse(text);
    return NextResponse.json({ ok: true, ...snapshot });
  } catch {
    return NextResponse.json(
      {
        ok: false,
        error: "No snapshot yet. Load the lab page in a browser first — it auto-reports on load and on resize.",
        hint: "GET /api/element-coords after visiting http://localhost:3000/vnc-click-lab",
      },
      { status: 404 }
    );
  }
}
