import { NextRequest, NextResponse } from "next/server";
import { appendFile, mkdir, readFile } from "node:fs/promises";
import path from "node:path";

const LOG_DIR = path.join(process.cwd(), "logs");
const LOG_PATH = path.join(LOG_DIR, "vnc-click-events.jsonl");

type EventType = "button_click" | "background_click" | "field_focus" | "field_input" | "field_keydown";

type LabPayload = {
  eventType?: EventType;
  buttonId?: string;
  label?: string;
  xPct?: number;
  yPct?: number;
  clickX?: number;
  clickY?: number;
  clickXPct?: number;
  clickYPct?: number;
  target?: string;
  fieldName?: string;
  fieldKind?: string;
  fieldValue?: string;
  key?: string;
  code?: string;
  page?: string;
  clickedAtClient?: string;
};

function asNumber(value: unknown): number | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return Number(value.toFixed(4));
}

function asString(value: unknown, maxLen = 300): string | null {
  if (typeof value !== "string") return null;
  return value.slice(0, maxLen);
}

export async function POST(req: NextRequest) {
  const body = (await req.json().catch(() => ({}))) as LabPayload;
  const eventType: EventType = body.eventType ?? "button_click";

  if (eventType === "button_click" && (!body.buttonId || !body.label)) {
    return NextResponse.json(
      { ok: false, error: "button_click requires buttonId and label" },
      { status: 400 }
    );
  }

  if ((eventType === "field_focus" || eventType === "field_input") && !body.fieldName) {
    return NextResponse.json(
      { ok: false, error: "field events require fieldName" },
      { status: 400 }
    );
  }

  const serverTs = new Date().toISOString();

  const entry = {
    event: eventType,
    loggedAt: serverTs,

    buttonId: asString(body.buttonId, 80),
    label: asString(body.label, 120),
    xPct: asNumber(body.xPct),
    yPct: asNumber(body.yPct),

    clickX: asNumber(body.clickX),
    clickY: asNumber(body.clickY),
    clickXPct: asNumber(body.clickXPct),
    clickYPct: asNumber(body.clickYPct),
    target: asString(body.target, 80),

    fieldName: asString(body.fieldName, 120),
    fieldKind: asString(body.fieldKind, 40),
    fieldValue: asString(body.fieldValue, 400),
    key: asString(body.key, 40),
    code: asString(body.code, 40),

    page: asString(body.page, 120) ?? "/vnc-click-lab",
    clientTs: asString(body.clickedAtClient, 60),
    requestId: crypto.randomUUID(),

    ip:
      req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ??
      req.headers.get("x-real-ip") ??
      "unknown",
    userAgent: req.headers.get("user-agent") ?? "unknown",
  };

  await mkdir(LOG_DIR, { recursive: true });
  await appendFile(LOG_PATH, `${JSON.stringify(entry)}\n`, "utf8");

  return NextResponse.json({
    ok: true,
    loggedAt: serverTs,
    requestId: entry.requestId,
    logPath: LOG_PATH,
    eventType,
  });
}

export async function GET(req: NextRequest) {
  const countRaw = req.nextUrl.searchParams.get("count") ?? "20";
  const count = Math.min(Math.max(Number.parseInt(countRaw, 10) || 20, 1), 500);

  try {
    const text = await readFile(LOG_PATH, "utf8");
    const lines = text.split("\n").filter(Boolean);
    const tail = lines.slice(-count).map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return { raw: line, parseError: true };
      }
    });

    return NextResponse.json({
      ok: true,
      path: LOG_PATH,
      totalLines: lines.length,
      count: tail.length,
      events: tail,
    });
  } catch {
    return NextResponse.json({ ok: true, path: LOG_PATH, totalLines: 0, count: 0, events: [] });
  }
}
