"use client";

import { useState } from "react";
import { useCoordReporter } from "../lib/useCoordReporter";

export default function FormsPage() {
  const { reportCoords, coordStatus } = useCoordReporter();
  const [submitted, setSubmitted] = useState(false);
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    department: "",
    role: "",
    notify_email: false,
    notify_sms: false,
    priority: "medium",
    notes: "",
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(true);
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Forms</h1>
          <p className="text-sm text-slate-400">
            Difficulty 2/6 — labels adjacent to elements, not inside them.
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
      <p className="mb-4 rounded bg-slate-900 px-3 py-2 text-xs text-slate-400">{coordStatus}</p>

      {submitted ? (
        <div
          data-element-id="success_banner"
          data-element-label="Form submitted successfully"
          data-element-kind="banner"
          className="rounded-xl border border-emerald-600 bg-emerald-900/40 p-6 text-center"
        >
          <p className="text-lg font-semibold text-emerald-300">✓ Form submitted</p>
          <button
            data-element-id="reset_btn"
            data-element-label="Submit another"
            data-element-kind="button"
            onClick={() => setSubmitted(false)}
            className="mt-4 rounded bg-slate-700 px-4 py-2 text-sm hover:bg-slate-600"
          >
            Submit another
          </button>
        </div>
      ) : (
        <form
          onSubmit={handleSubmit}
          className="space-y-5 rounded-xl border border-slate-700 bg-slate-900 p-6"
        >
          {/* Text inputs */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm text-slate-300" htmlFor="full_name">
                Full Name
              </label>
              <input
                id="full_name"
                data-element-id="input_full_name"
                data-element-label="Full Name input"
                data-element-kind="input"
                type="text"
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                placeholder="Jane Smith"
                className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white placeholder-slate-600"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-300" htmlFor="email">
                Email Address
              </label>
              <input
                id="email"
                data-element-id="input_email"
                data-element-label="Email Address input"
                data-element-kind="input"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                placeholder="jane@example.com"
                className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white placeholder-slate-600"
              />
            </div>
          </div>

          {/* Selects */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm text-slate-300" htmlFor="department">
                Department
              </label>
              <select
                id="department"
                data-element-id="select_department"
                data-element-label="Department select"
                data-element-kind="select"
                value={form.department}
                onChange={(e) => setForm({ ...form, department: e.target.value })}
                className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value="">Select department…</option>
                <option value="eng">Engineering</option>
                <option value="design">Design</option>
                <option value="product">Product</option>
                <option value="ops">Operations</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-300" htmlFor="role">
                Role
              </label>
              <select
                id="role"
                data-element-id="select_role"
                data-element-label="Role select"
                data-element-kind="select"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
                className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value="">Select role…</option>
                <option value="ic">Individual Contributor</option>
                <option value="lead">Lead</option>
                <option value="manager">Manager</option>
                <option value="director">Director</option>
              </select>
            </div>
          </div>

          {/* Checkboxes */}
          <fieldset>
            <legend className="mb-2 text-sm text-slate-300">Notifications</legend>
            <div className="flex gap-6">
              <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
                <input
                  id="notify_email"
                  data-element-id="checkbox_notify_email"
                  data-element-label="Email notifications checkbox"
                  data-element-kind="checkbox"
                  type="checkbox"
                  checked={form.notify_email}
                  onChange={(e) => setForm({ ...form, notify_email: e.target.checked })}
                  className="h-4 w-4 accent-violet-500"
                />
                Email
              </label>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
                <input
                  id="notify_sms"
                  data-element-id="checkbox_notify_sms"
                  data-element-label="SMS notifications checkbox"
                  data-element-kind="checkbox"
                  type="checkbox"
                  checked={form.notify_sms}
                  onChange={(e) => setForm({ ...form, notify_sms: e.target.checked })}
                  className="h-4 w-4 accent-violet-500"
                />
                SMS
              </label>
            </div>
          </fieldset>

          {/* Radio buttons */}
          <fieldset>
            <legend className="mb-2 text-sm text-slate-300">Priority</legend>
            <div className="flex gap-6">
              {(["low", "medium", "high", "critical"] as const).map((p) => (
                <label key={p} className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
                  <input
                    id={`priority_${p}`}
                    data-element-id={`radio_priority_${p}`}
                    data-element-label={`Priority ${p} radio`}
                    data-element-kind="radio"
                    type="radio"
                    name="priority"
                    value={p}
                    checked={form.priority === p}
                    onChange={() => setForm({ ...form, priority: p })}
                    className="accent-violet-500"
                  />
                  {p.charAt(0).toUpperCase() + p.slice(1)}
                </label>
              ))}
            </div>
          </fieldset>

          {/* Textarea */}
          <div>
            <label className="mb-1 block text-sm text-slate-300" htmlFor="notes">
              Notes
            </label>
            <textarea
              id="notes"
              data-element-id="textarea_notes"
              data-element-label="Notes textarea"
              data-element-kind="textarea"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Any additional context…"
              rows={3}
              className="w-full rounded border border-slate-600 bg-slate-950 px-3 py-2 text-sm text-white placeholder-slate-600"
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              data-element-id="btn_submit"
              data-element-label="Submit button"
              data-element-kind="button"
              className="rounded bg-violet-600 px-5 py-2 text-sm font-semibold hover:bg-violet-500"
            >
              Submit
            </button>
            <button
              type="button"
              data-element-id="btn_clear"
              data-element-label="Clear form button"
              data-element-kind="button"
              onClick={() =>
                setForm({
                  full_name: "", email: "", department: "", role: "",
                  notify_email: false, notify_sms: false, priority: "medium", notes: "",
                })
              }
              className="rounded bg-slate-700 px-5 py-2 text-sm font-semibold hover:bg-slate-600"
            >
              Clear
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
