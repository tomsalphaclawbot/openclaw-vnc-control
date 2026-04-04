"use client";

import { useState } from "react";
import { useCoordReporter } from "../lib/useCoordReporter";

type ModalKind = "confirm" | "form" | "alert" | null;

export default function ModalsPage() {
  const { reportCoords, coordStatus } = useCoordReporter();
  const [openModal, setOpenModal] = useState<ModalKind>(null);
  const [lastAction, setLastAction] = useState("—");
  const [formVal, setFormVal] = useState("");

  function close(action: string) {
    setLastAction(action);
    setOpenModal(null);
    // Re-report coords after modal closes (elements change)
    setTimeout(() => void reportCoords(), 150);
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Modals</h1>
          <p className="text-sm text-slate-400">
            Difficulty 4/6 — target elements appear only after a trigger. Context-dependent disambiguation.
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
        Last action: <span className="text-white">{lastAction}</span> — {coordStatus}
      </p>

      {/* Trigger buttons */}
      <div className="grid gap-4 sm:grid-cols-3">
        <button
          data-element-id="btn_open_confirm_modal"
          data-element-label="Open Confirm modal"
          data-element-kind="button"
          onClick={() => { setOpenModal("confirm"); void reportCoords(); }}
          className="rounded-xl border border-slate-600 bg-slate-800 px-4 py-6 text-sm font-semibold hover:border-violet-500 hover:bg-slate-700 transition"
        >
          Open Confirm Modal
        </button>
        <button
          data-element-id="btn_open_form_modal"
          data-element-label="Open Form modal"
          data-element-kind="button"
          onClick={() => { setOpenModal("form"); void reportCoords(); }}
          className="rounded-xl border border-slate-600 bg-slate-800 px-4 py-6 text-sm font-semibold hover:border-violet-500 hover:bg-slate-700 transition"
        >
          Open Form Modal
        </button>
        <button
          data-element-id="btn_open_alert_modal"
          data-element-label="Open Alert modal"
          data-element-kind="button"
          onClick={() => { setOpenModal("alert"); void reportCoords(); }}
          className="rounded-xl border border-slate-600 bg-slate-800 px-4 py-6 text-sm font-semibold hover:border-violet-500 hover:bg-slate-700 transition"
        >
          Open Alert Modal
        </button>
      </div>

      {/* Overlay */}
      {openModal && (
        <div
          data-element-id="modal_overlay"
          data-element-label="Modal overlay backdrop"
          data-element-kind="overlay"
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/70"
          onClick={() => close("Dismissed (backdrop)")}
        >
          {/* ── Confirm modal ── */}
          {openModal === "confirm" && (
            <div
              data-element-id="modal_confirm"
              data-element-label="Confirm dialog"
              data-element-kind="modal"
              className="relative z-50 w-96 rounded-2xl border border-slate-600 bg-slate-900 p-6 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                data-element-id="modal_confirm_close_x"
                data-element-label="Close Confirm modal X button"
                data-element-kind="icon-button"
                onClick={() => close("Confirm modal — closed via ×")}
                className="absolute right-4 top-4 rounded p-1 text-slate-400 hover:text-white"
              >
                ✕
              </button>
              <h2 className="mb-2 text-lg font-bold">Delete this item?</h2>
              <p className="mb-6 text-sm text-slate-400">
                This action is permanent and cannot be undone.
              </p>
              <div className="flex gap-3">
                <button
                  data-element-id="modal_confirm_delete_btn"
                  data-element-label="Confirm Delete button"
                  data-element-kind="button"
                  onClick={() => close("Confirm modal — Delete confirmed")}
                  className="flex-1 rounded bg-rose-600 py-2 text-sm font-semibold hover:bg-rose-500"
                >
                  Delete
                </button>
                <button
                  data-element-id="modal_confirm_cancel_btn"
                  data-element-label="Cancel button"
                  data-element-kind="button"
                  onClick={() => close("Confirm modal — cancelled")}
                  className="flex-1 rounded bg-slate-700 py-2 text-sm font-semibold hover:bg-slate-600"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* ── Form modal ── */}
          {openModal === "form" && (
            <div
              data-element-id="modal_form"
              data-element-label="Form dialog"
              data-element-kind="modal"
              className="relative z-50 w-96 rounded-2xl border border-slate-600 bg-slate-900 p-6 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                data-element-id="modal_form_close_x"
                data-element-label="Close Form modal X button"
                data-element-kind="icon-button"
                onClick={() => close("Form modal — closed via ×")}
                className="absolute right-4 top-4 rounded p-1 text-slate-400 hover:text-white"
              >
                ✕
              </button>
              <h2 className="mb-4 text-lg font-bold">Rename item</h2>
              <label className="mb-1 block text-sm text-slate-300">New name</label>
              <input
                data-element-id="modal_form_input"
                data-element-label="Rename input field"
                data-element-kind="input"
                type="text"
                value={formVal}
                onChange={(e) => setFormVal(e.target.value)}
                placeholder="Enter new name…"
                className="mb-5 w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white"
              />
              <div className="flex gap-3">
                <button
                  data-element-id="modal_form_save_btn"
                  data-element-label="Save button"
                  data-element-kind="button"
                  onClick={() => close(`Form modal — saved "${formVal}"`)}
                  className="flex-1 rounded bg-violet-600 py-2 text-sm font-semibold hover:bg-violet-500"
                >
                  Save
                </button>
                <button
                  data-element-id="modal_form_cancel_btn"
                  data-element-label="Cancel button"
                  data-element-kind="button"
                  onClick={() => close("Form modal — cancelled")}
                  className="rounded bg-slate-700 px-4 py-2 text-sm font-semibold hover:bg-slate-600"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* ── Alert modal ── */}
          {openModal === "alert" && (
            <div
              data-element-id="modal_alert"
              data-element-label="Alert dialog"
              data-element-kind="modal"
              className="relative z-50 w-80 rounded-2xl border border-amber-600 bg-slate-900 p-6 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <p className="mb-1 text-sm font-bold text-amber-400">⚠ Warning</p>
              <p className="mb-5 text-sm text-slate-300">
                Your session is about to expire. Save your work.
              </p>
              <button
                data-element-id="modal_alert_ok_btn"
                data-element-label="OK dismiss alert button"
                data-element-kind="button"
                onClick={() => close("Alert modal — dismissed")}
                className="w-full rounded bg-amber-600 py-2 text-sm font-semibold hover:bg-amber-500"
              >
                OK, got it
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
