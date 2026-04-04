"use client";

import { useState } from "react";
import { useCoordReporter } from "../lib/useCoordReporter";

// 48 buttons in a tight grid. Labels are "Button 1" through "Button 48".
// Neighboring buttons are visually similar — model must use position + number.
const TOTAL = 48;

const TONES = [
  "bg-slate-700 hover:bg-slate-600",
  "bg-slate-800 hover:bg-slate-700",
];

export default function DensityPage() {
  const { reportCoords, coordStatus } = useCoordReporter();
  const [lastClicked, setLastClicked] = useState("—");
  const [highlight, setHighlight] = useState<number | null>(null);

  // Randomly highlight a target button every time user clicks "Pick random"
  function pickRandom() {
    setHighlight(Math.floor(Math.random() * TOTAL) + 1);
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Density</h1>
          <p className="text-sm text-slate-400">
            Difficulty 5/6 — 48 small, tightly-packed buttons with similar labels. Requires
            fine-grained spatial reasoning to distinguish neighbors.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            data-element-id="btn_pick_random"
            data-element-label="Pick random target button"
            data-element-kind="button"
            onClick={pickRandom}
            className="rounded bg-amber-700 px-3 py-2 text-xs font-semibold hover:bg-amber-600"
          >
            🎯 Pick Random
          </button>
          <button
            data-element-id="report_coords_btn"
            data-element-label="Report Coords"
            data-element-kind="button"
            onClick={() => void reportCoords()}
            className="rounded bg-violet-700 px-3 py-2 text-xs font-semibold hover:bg-violet-600"
          >
            📍 Report Coords
          </button>
        </div>
      </div>

      <p className="mb-4 rounded bg-slate-900 px-3 py-2 text-xs text-slate-400">
        {highlight !== null ? (
          <>
            Target: <span className="font-bold text-amber-300">Button {highlight}</span> —{" "}
          </>
        ) : null}
        Last clicked: <span className="text-white">{lastClicked}</span> — {coordStatus}
      </p>

      <div className="rounded-xl border border-slate-700 bg-slate-900 p-4">
        <div className="grid grid-cols-8 gap-1.5">
          {Array.from({ length: TOTAL }, (_, i) => {
            const n = i + 1;
            const isTarget = highlight === n;
            return (
              <button
                key={n}
                id={`density_btn_${n}`}
                data-element-id={`density_btn_${n}`}
                data-element-label={`Button ${n}`}
                data-element-kind="density-button"
                onClick={() => {
                  setLastClicked(`Button ${n}`);
                  if (highlight === n) setHighlight(null);
                }}
                className={`rounded px-1 py-2 text-xs font-medium transition
                  ${isTarget
                    ? "bg-amber-500 text-black ring-2 ring-amber-300 hover:bg-amber-400"
                    : TONES[i % 2]
                  } text-white`}
              >
                {n}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-slate-700 bg-slate-900 p-4">
        <p className="mb-3 text-xs font-semibold text-slate-400">
          Harder variant — buttons labeled with similar two-word phrases:
        </p>
        <div className="grid grid-cols-6 gap-1.5">
          {[
            "Alpha One", "Alpha Two", "Alpha Three",
            "Beta One",  "Beta Two",  "Beta Three",
            "Gamma One", "Gamma Two", "Gamma Three",
            "Delta One", "Delta Two", "Delta Three",
          ].map((label, i) => {
            const id = `density_phrase_${label.toLowerCase().replace(/\s+/g, "_")}`;
            return (
              <button
                key={id}
                id={id}
                data-element-id={id}
                data-element-label={label}
                data-element-kind="density-phrase-button"
                onClick={() => setLastClicked(label)}
                className="rounded bg-slate-700 px-2 py-2 text-xs font-medium text-white hover:bg-slate-600 transition"
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
