"use client";

import { useState } from "react";
import { useCoordReporter } from "../lib/useCoordReporter";

// SVG icons — inline to avoid external deps
const ICONS = {
  edit: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  ),
  delete: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  ),
  copy: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  ),
  share: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" />
      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
    </svg>
  ),
  pin: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  ),
  star: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  ),
  download: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  ),
  archive: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <polyline points="21 8 21 21 3 21 3 8" />
      <rect x="1" y="3" width="22" height="5" />
      <line x1="10" y1="12" x2="14" y2="12" />
    </svg>
  ),
  close: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  ),
  check: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  search: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  ),
  settings: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-5 w-5">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  ),
};

type IconName = keyof typeof ICONS;

const ROWS: { id: string; label: string; icon: IconName; color: string }[][] = [
  [
    { id: "icon_edit", label: "Edit", icon: "edit", color: "bg-sky-800 hover:bg-sky-700" },
    { id: "icon_delete", label: "Delete", icon: "delete", color: "bg-rose-800 hover:bg-rose-700" },
    { id: "icon_copy", label: "Copy", icon: "copy", color: "bg-slate-700 hover:bg-slate-600" },
    { id: "icon_share", label: "Share", icon: "share", color: "bg-emerald-800 hover:bg-emerald-700" },
    { id: "icon_pin", label: "Pin", icon: "pin", color: "bg-amber-800 hover:bg-amber-700" },
    { id: "icon_star", label: "Star", icon: "star", color: "bg-yellow-800 hover:bg-yellow-700" },
  ],
  [
    { id: "icon_download", label: "Download", icon: "download", color: "bg-indigo-800 hover:bg-indigo-700" },
    { id: "icon_archive", label: "Archive", icon: "archive", color: "bg-slate-700 hover:bg-slate-600" },
    { id: "icon_close", label: "Close", icon: "close", color: "bg-red-800 hover:bg-red-700" },
    { id: "icon_check", label: "Confirm", icon: "check", color: "bg-emerald-800 hover:bg-emerald-700" },
    { id: "icon_search", label: "Search", icon: "search", color: "bg-violet-800 hover:bg-violet-700" },
    { id: "icon_settings", label: "Settings", icon: "settings", color: "bg-slate-700 hover:bg-slate-600" },
  ],
];

export default function IconsPage() {
  const { reportCoords, coordStatus } = useCoordReporter();
  const [lastClicked, setLastClicked] = useState<string>("—");

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Icons</h1>
          <p className="text-sm text-slate-400">
            Difficulty 3/6 — small icon-only buttons (~40px). No text label. Reason from shape.
          </p>
        </div>
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
      <p className="mb-6 rounded bg-slate-900 px-3 py-2 text-xs text-slate-400">
        Last clicked: <span className="text-white">{lastClicked}</span> — {coordStatus}
      </p>

      <div className="rounded-xl border border-slate-700 bg-slate-900 p-8">
        <p className="mb-6 text-xs text-slate-500 text-center">
          Icon-only toolbar — no visible labels. The benchmark will ask models to find "the delete button", "the settings button", etc.
        </p>

        {ROWS.map((row, ri) => (
          <div key={ri} className="mb-6 flex justify-center gap-4">
            {row.map((btn) => (
              <button
                key={btn.id}
                id={btn.id}
                data-element-id={btn.id}
                data-element-label={`${btn.label} icon button`}
                data-element-kind="icon-button"
                title={btn.label} // tooltip only visible on hover, not in screenshot
                onClick={() => setLastClicked(`${btn.label} (${btn.id})`)}
                className={`rounded-lg p-2.5 text-white transition ${btn.color}`}
              >
                {ICONS[btn.icon]}
              </button>
            ))}
          </div>
        ))}

        {/* Harder variant: same icon, two different actions */}
        <div className="mt-8 border-t border-slate-700 pt-6">
          <p className="mb-4 text-xs text-slate-400 text-center">
            Hard variant — two close icons with different contexts:
          </p>
          <div className="flex items-center justify-center gap-16">
            <div className="flex flex-col items-center gap-2">
              <span className="text-xs text-slate-500">Dialog A</span>
              <button
                id="icon_close_dialog_a"
                data-element-id="icon_close_dialog_a"
                data-element-label="Close Dialog A icon button"
                data-element-kind="icon-button"
                onClick={() => setLastClicked("Close Dialog A")}
                className="rounded-lg bg-slate-700 p-2.5 text-white hover:bg-slate-600"
              >
                {ICONS.close}
              </button>
            </div>
            <div className="flex flex-col items-center gap-2">
              <span className="text-xs text-slate-500">Dialog B</span>
              <button
                id="icon_close_dialog_b"
                data-element-id="icon_close_dialog_b"
                data-element-label="Close Dialog B icon button"
                data-element-kind="icon-button"
                onClick={() => setLastClicked("Close Dialog B")}
                className="rounded-lg bg-slate-700 p-2.5 text-white hover:bg-slate-600"
              >
                {ICONS.close}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
