"use client";

import { useMemo, useRef, useState } from "react";

type ButtonDef = {
  id: string;
  label: string;
  xPct: number;
  yPct: number;
  tone: string;
};

type LabEventPayload = {
  eventType: "button_click" | "background_click" | "field_focus" | "field_input" | "field_keydown";
  page: string;
  clickedAtClient: string;
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
  fieldKind?: "input" | "text";
  fieldValue?: string;
  key?: string;
  code?: string;
};

const LABELS = [
  "QUIET LASER",
  "MANGO CIRCUIT",
  "NOVA PAPER",
  "RUSTY COMET",
  "VELVET SPARK",
  "TANGO FROST",
  "ATLAS PLUM",
  "PIXEL THUNDER",
  "VIOLET ANCHOR",
  "SILVER JUNGLE",
  "BRISK CANYON",
  "MAGNET OCEAN",
  "RAPID SAND",
  "EMBER BLOOM",
  "MIDNIGHT BANJO",
  "TINY SATURN",
  "PLASMA KOALA",
  "COPPER WAVE",
  "NEON PEBBLE",
  "GHOST PEPPER",
  "CRISP ROCKET",
  "MARBLE PULSE",
];

const TONES = [
  "bg-sky-500 hover:bg-sky-400",
  "bg-indigo-500 hover:bg-indigo-400",
  "bg-emerald-500 hover:bg-emerald-400",
  "bg-fuchsia-500 hover:bg-fuchsia-400",
  "bg-amber-500 hover:bg-amber-400",
  "bg-rose-500 hover:bg-rose-400",
  "bg-cyan-500 hover:bg-cyan-400",
  "bg-purple-500 hover:bg-purple-400",
];

function buildButtons(): ButtonDef[] {
  // Deterministic non-overlapping grid that stays clear of the top-left typing panel.
  const cols = 6;
  const rows = 4;
  const startX = 40;
  const endX = 90;
  const startY = 22;
  const endY = 88;

  const xStep = (endX - startX) / (cols - 1);
  const yStep = (endY - startY) / (rows - 1);

  const slots: Array<{ xPct: number; yPct: number }> = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      slots.push({
        xPct: Number((startX + c * xStep).toFixed(2)),
        yPct: Number((startY + r * yStep).toFixed(2)),
      });
    }
  }

  return LABELS.map((label, idx) => {
    const slot = slots[idx];
    return {
      id: `btn-${idx + 1}`,
      label,
      xPct: slot.xPct,
      yPct: slot.yPct,
      tone: TONES[idx % TONES.length],
    };
  });
}

export default function VncClickLabPage() {
  const buttons = useMemo(() => buildButtons(), []);
  const labRef = useRef<HTMLElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const textRef = useRef<HTMLTextAreaElement | null>(null);

  const [lastEvent, setLastEvent] = useState<string>("No events yet");
  const [isBusy, setIsBusy] = useState(false);
  const [agentInput, setAgentInput] = useState("");
  const [agentText, setAgentText] = useState("");

  function sectionMeta(clientX: number, clientY: number) {
    const rect = labRef.current?.getBoundingClientRect();
    if (!rect) {
      return {
        clickX: null,
        clickY: null,
        clickXPct: null,
        clickYPct: null,
      };
    }

    const relX = Math.max(0, Math.min(rect.width, clientX - rect.left));
    const relY = Math.max(0, Math.min(rect.height, clientY - rect.top));

    return {
      clickX: Number(relX.toFixed(2)),
      clickY: Number(relY.toFixed(2)),
      clickXPct: Number(((relX / rect.width) * 100).toFixed(4)),
      clickYPct: Number(((relY / rect.height) * 100).toFixed(4)),
    };
  }

  async function logLabEvent(payload: LabEventPayload, successText: string) {
    setIsBusy(true);
    try {
      const res = await fetch("/api/vnc-click-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      setLastEvent(`${successText} at ${data.loggedAt}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "unknown error";
      setLastEvent(`FAILED log (${payload.eventType}): ${msg}`);
    } finally {
      setIsBusy(false);
    }
  }

  async function handleButtonClick(btn: ButtonDef, e: React.MouseEvent<HTMLButtonElement>) {
    e.stopPropagation();
    const meta = sectionMeta(e.clientX, e.clientY);

    await logLabEvent(
      {
        eventType: "button_click",
        buttonId: btn.id,
        label: btn.label,
        xPct: btn.xPct,
        yPct: btn.yPct,
        page: "/vnc-click-lab",
        clickedAtClient: new Date().toISOString(),
        ...meta,
        target: "button",
      },
      `Logged ${btn.id} (${btn.label})`
    );
  }

  async function handleBackgroundClick(e: React.MouseEvent<HTMLElement>) {
    if (e.target !== e.currentTarget) return;
    const meta = sectionMeta(e.clientX, e.clientY);

    await logLabEvent(
      {
        eventType: "background_click",
        page: "/vnc-click-lab",
        clickedAtClient: new Date().toISOString(),
        ...meta,
        target: "background",
      },
      `Logged background click @ (${meta.clickX}, ${meta.clickY})`
    );
  }

  async function logFieldFocus(fieldName: string, fieldKind: "input" | "text") {
    await logLabEvent(
      {
        eventType: "field_focus",
        fieldName,
        fieldKind,
        page: "/vnc-click-lab",
        clickedAtClient: new Date().toISOString(),
        target: "field",
      },
      `Logged field focus: ${fieldName}`
    );
  }

  async function logFieldInput(fieldName: string, fieldKind: "input" | "text", value: string) {
    await logLabEvent(
      {
        eventType: "field_input",
        fieldName,
        fieldKind,
        fieldValue: value.slice(0, 200),
        page: "/vnc-click-lab",
        clickedAtClient: new Date().toISOString(),
        target: "field",
      },
      `Logged field input: ${fieldName}`
    );
  }

  async function logFieldKeydown(fieldName: string, fieldKind: "input" | "text", key: string, code: string) {
    await logLabEvent(
      {
        eventType: "field_keydown",
        fieldName,
        fieldKind,
        key,
        code,
        page: "/vnc-click-lab",
        clickedAtClient: new Date().toISOString(),
        target: "field",
      },
      `Logged field key: ${fieldName} ${key}`
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-6xl px-4 py-4">
        <h1 className="text-2xl font-bold">VNC Click Accuracy Lab</h1>
        <p className="mt-1 text-sm text-slate-300">
          22 distributed buttons + named typing fields. Every button click, field event, and background
          click is logged to server-side JSONL.
        </p>
        <p className="mt-2 rounded bg-slate-900/80 px-3 py-2 text-xs text-slate-200">
          {lastEvent}
          {isBusy ? " (logging...)" : ""}
        </p>
      </div>

      <section
        ref={labRef}
        onClick={handleBackgroundClick}
        className="relative mx-4 mb-6 h-[78vh] rounded-xl border border-slate-700 bg-slate-900"
      >
        <div
          className="absolute left-3 top-3 z-20 w-[30rem] rounded-lg border border-slate-600 bg-slate-800/90 p-3"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="mb-2 text-xs font-semibold text-slate-200">Typing Targets</p>
          <div className="mb-3 grid grid-cols-2 gap-2">
            <button
              id="focus_agent_input"
              className="rounded bg-sky-700 px-2 py-1 text-xs font-semibold text-white hover:bg-sky-600"
              onClick={(e) => {
                e.stopPropagation();
                inputRef.current?.focus();
                void logFieldFocus("agent_input", "input");
              }}
            >
              Focus agent_input
            </button>
            <button
              id="focus_agent_text_field"
              className="rounded bg-emerald-700 px-2 py-1 text-xs font-semibold text-white hover:bg-emerald-600"
              onClick={(e) => {
                e.stopPropagation();
                textRef.current?.focus();
                void logFieldFocus("agent_text_field", "text");
              }}
            >
              Focus agent_text_field
            </button>
          </div>

          <label className="mb-2 block text-xs text-slate-300" htmlFor="agent_input">
            Named input field: <span className="font-mono text-sky-300">agent_input</span>
          </label>
          <input
            ref={inputRef}
            id="agent_input"
            name="agent_input"
            value={agentInput}
            onChange={(e) => setAgentInput(e.target.value)}
            onFocus={() => {
              void logFieldFocus("agent_input", "input");
            }}
            onBlur={() => {
              void logFieldInput("agent_input", "input", agentInput);
            }}
            onKeyDown={(e) => {
              void logFieldKeydown("agent_input", "input", e.key, e.code);
            }}
            onClick={(e) => e.stopPropagation()}
            className="mb-3 w-full rounded border border-slate-500 bg-slate-950 px-2 py-1 text-sm text-white"
            placeholder="Type into named input field"
          />

          <label className="mb-2 block text-xs text-slate-300" htmlFor="agent_text_field">
            Named text field: <span className="font-mono text-emerald-300">agent_text_field</span>
          </label>
          <textarea
            ref={textRef}
            id="agent_text_field"
            name="agent_text_field"
            value={agentText}
            onChange={(e) => setAgentText(e.target.value)}
            onFocus={() => {
              void logFieldFocus("agent_text_field", "text");
            }}
            onBlur={() => {
              void logFieldInput("agent_text_field", "text", agentText);
            }}
            onKeyDown={(e) => {
              void logFieldKeydown("agent_text_field", "text", e.key, e.code);
            }}
            onClick={(e) => e.stopPropagation()}
            className="h-20 w-full rounded border border-slate-500 bg-slate-950 px-2 py-1 text-sm text-white"
            placeholder="Type into named text field"
          />
        </div>

        {buttons.map((btn) => (
          <button
            key={btn.id}
            onClick={(e) => {
              void handleButtonClick(btn, e);
            }}
            style={{ left: `${btn.xPct}%`, top: `${btn.yPct}%` }}
            className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-md px-3 py-2 text-xs font-semibold tracking-wide shadow-lg transition ${btn.tone}`}
            title={`${btn.id} @ ${btn.xPct}%,${btn.yPct}%`}
          >
            {btn.label}
          </button>
        ))}
      </section>
    </main>
  );
}
