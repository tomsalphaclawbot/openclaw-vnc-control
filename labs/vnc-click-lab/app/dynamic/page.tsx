"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useCoordReporter } from "../lib/useCoordReporter";

type Phase = "idle" | "counting" | "visible" | "expired";

export default function DynamicPage() {
  const { reportCoords, coordStatus } = useCoordReporter();
  const [lastAction, setLastAction] = useState("—");

  // ── Scenario A: timed button ──────────────────────────────────────────────
  // Click "Start" → 5s countdown → button appears for 4s → disappears.
  // Tests: wait_for "Click me" button.
  const [phaseA, setPhaseA] = useState<Phase>("idle");
  const [countA, setCountA] = useState(5);
  const timerA = useRef<ReturnType<typeof setInterval> | null>(null);

  function startA() {
    setPhaseA("counting");
    setCountA(5);
    timerA.current = setInterval(() => {
      setCountA((c) => {
        if (c <= 1) {
          clearInterval(timerA.current!);
          setPhaseA("visible");
          void reportCoords();
          // Auto-expire after 4s
          setTimeout(() => {
            setPhaseA("expired");
            void reportCoords();
          }, 4000);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  }

  function resetA() {
    clearInterval(timerA.current!);
    setPhaseA("idle");
    setCountA(5);
  }

  useEffect(() => () => clearInterval(timerA.current!), []);

  // ── Scenario B: rotating alert ────────────────────────────────────────────
  // A dismissible toast pops up every 6s. Tests: wait_for "Dismiss" button.
  const [alertVisible, setAlertVisible] = useState(false);
  const [alertCount, setAlertCount] = useState(0);
  const alertTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const [alertRunning, setAlertRunning] = useState(false);

  const startAlerts = useCallback(() => {
    setAlertRunning(true);
    setAlertVisible(true);
    setAlertCount((c) => c + 1);
    void reportCoords();
    alertTimer.current = setInterval(() => {
      setAlertVisible(true);
      setAlertCount((c) => c + 1);
      void reportCoords();
    }, 6000);
  }, [reportCoords]);

  function dismissAlert() {
    setAlertVisible(false);
    setLastAction("Dismissed alert");
    void reportCoords();
  }

  function stopAlerts() {
    clearInterval(alertTimer.current!);
    setAlertVisible(false);
    setAlertRunning(false);
  }

  useEffect(() => () => clearInterval(alertTimer.current!), []);

  // ── Scenario C: toggling elements ─────────────────────────────────────────
  // Three buttons that independently toggle their sibling element.
  // Tests: assert_visible / wait_for after interaction.
  const [toggles, setToggles] = useState([false, false, false]);

  function flip(i: number) {
    setToggles((t) => {
      const next = [...t];
      next[i] = !next[i];
      return next;
    });
    setTimeout(() => void reportCoords(), 50);
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Dynamic</h1>
          <p className="text-sm text-slate-400">
            Difficulty 6/6 — elements appear and disappear. Tests{" "}
            <code className="rounded bg-slate-800 px-1 text-violet-300">wait_for</code> and{" "}
            <code className="rounded bg-slate-800 px-1 text-violet-300">assert_visible</code>.
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

      {/* ── Scenario A ── */}
      <section className="mb-6 rounded-xl border border-slate-700 bg-slate-900 p-5">
        <h2 className="mb-1 font-semibold">Scenario A — Timed Button</h2>
        <p className="mb-4 text-xs text-slate-400">
          Click Start → wait 5s → button appears for 4s → expires. Use{" "}
          <code className="text-violet-300">wait_for &quot;Click me now&quot;</code>.
        </p>

        <div className="flex items-center gap-4">
          {phaseA === "idle" && (
            <button
              data-element-id="scenario_a_start"
              data-element-label="Start scenario A"
              data-element-kind="button"
              onClick={startA}
              className="rounded bg-sky-700 px-4 py-2 text-sm font-semibold hover:bg-sky-600"
            >
              Start
            </button>
          )}

          {phaseA === "counting" && (
            <div
              data-element-id="scenario_a_countdown"
              data-element-label="Countdown timer"
              data-element-kind="status"
              className="flex items-center gap-3"
            >
              <span className="text-2xl font-bold text-slate-300">{countA}</span>
              <span className="text-sm text-slate-500">seconds until button appears…</span>
              <button
                data-element-id="scenario_a_cancel"
                data-element-label="Cancel countdown"
                data-element-kind="button"
                onClick={resetA}
                className="rounded bg-slate-700 px-3 py-1 text-xs hover:bg-slate-600"
              >
                Cancel
              </button>
            </div>
          )}

          {phaseA === "visible" && (
            <button
              data-element-id="scenario_a_target_btn"
              data-element-label="Click me now"
              data-element-kind="button"
              onClick={() => { setLastAction("Clicked 'Click me now'"); resetA(); }}
              className="animate-pulse rounded-lg bg-emerald-500 px-6 py-3 text-sm font-bold text-black hover:bg-emerald-400"
            >
              Click me now
            </button>
          )}

          {phaseA === "expired" && (
            <div className="flex items-center gap-3">
              <span className="text-sm text-rose-400">⏱ Expired — too slow</span>
              <button
                data-element-id="scenario_a_retry"
                data-element-label="Try again button"
                data-element-kind="button"
                onClick={resetA}
                className="rounded bg-slate-700 px-3 py-1 text-xs hover:bg-slate-600"
              >
                Try again
              </button>
            </div>
          )}
        </div>
      </section>

      {/* ── Scenario B ── */}
      <section className="mb-6 rounded-xl border border-slate-700 bg-slate-900 p-5">
        <h2 className="mb-1 font-semibold">Scenario B — Rotating Alert</h2>
        <p className="mb-4 text-xs text-slate-400">
          A dismissible toast appears every 6s. Use{" "}
          <code className="text-violet-300">wait_for &quot;Dismiss&quot;</code> then click it.
        </p>

        <div className="flex items-center gap-3">
          {!alertRunning ? (
            <button
              data-element-id="scenario_b_start"
              data-element-label="Start rotating alerts"
              data-element-kind="button"
              onClick={startAlerts}
              className="rounded bg-sky-700 px-4 py-2 text-sm font-semibold hover:bg-sky-600"
            >
              Start Alerts
            </button>
          ) : (
            <button
              data-element-id="scenario_b_stop"
              data-element-label="Stop alerts"
              data-element-kind="button"
              onClick={stopAlerts}
              className="rounded bg-slate-700 px-4 py-2 text-sm font-semibold hover:bg-slate-600"
            >
              Stop
            </button>
          )}
          {alertRunning && (
            <span className="text-xs text-slate-500">Alert #{alertCount} — next in ~6s</span>
          )}
        </div>

        {alertVisible && (
          <div
            data-element-id="scenario_b_alert"
            data-element-label="Rotating alert toast"
            data-element-kind="alert"
            className="mt-4 flex items-center justify-between rounded-lg border border-amber-600 bg-amber-900/30 px-4 py-3"
          >
            <span className="text-sm text-amber-200">⚠ Alert #{alertCount}: action required</span>
            <button
              data-element-id="scenario_b_dismiss"
              data-element-label="Dismiss alert"
              data-element-kind="button"
              onClick={dismissAlert}
              className="rounded bg-amber-700 px-3 py-1 text-xs font-semibold hover:bg-amber-600"
            >
              Dismiss
            </button>
          </div>
        )}
      </section>

      {/* ── Scenario C ── */}
      <section className="rounded-xl border border-slate-700 bg-slate-900 p-5">
        <h2 className="mb-1 font-semibold">Scenario C — Toggle Panels</h2>
        <p className="mb-4 text-xs text-slate-400">
          Each toggle button shows/hides a sibling panel. Use{" "}
          <code className="text-violet-300">assert_visible &quot;Panel B content&quot;</code> after toggling.
        </p>

        <div className="space-y-3">
          {(["A", "B", "C"] as const).map((letter, i) => (
            <div key={letter} className="rounded-lg border border-slate-700">
              <button
                data-element-id={`scenario_c_toggle_${letter.toLowerCase()}`}
                data-element-label={`Toggle Panel ${letter}`}
                data-element-kind="button"
                onClick={() => flip(i)}
                className="flex w-full items-center justify-between rounded-lg px-4 py-3 text-sm font-semibold hover:bg-slate-800 transition"
              >
                <span>Panel {letter}</span>
                <span className="text-slate-400">{toggles[i] ? "▲" : "▼"}</span>
              </button>
              {toggles[i] && (
                <div
                  data-element-id={`scenario_c_panel_${letter.toLowerCase()}_content`}
                  data-element-label={`Panel ${letter} content`}
                  data-element-kind="panel"
                  className="border-t border-slate-700 px-4 py-3 text-sm text-slate-400"
                >
                  Panel {letter} is now visible. This element only exists in the DOM when the panel
                  is open — assert_visible should return true right now.
                  <button
                    data-element-id={`scenario_c_panel_${letter.toLowerCase()}_action`}
                    data-element-label={`Panel ${letter} action button`}
                    data-element-kind="button"
                    onClick={() => setLastAction(`Panel ${letter} action`)}
                    className="ml-3 rounded bg-slate-700 px-2 py-0.5 text-xs hover:bg-slate-600"
                  >
                    Action
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
