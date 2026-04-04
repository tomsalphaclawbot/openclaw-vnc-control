import Link from "next/link";

const SCENARIOS = [
  {
    href: "/vnc-click-lab",
    title: "Grid (Easy)",
    difficulty: 1,
    description:
      "22 large, distinctly-labeled, color-coded buttons in a 6×4 grid. Baseline accuracy test. All targets are obvious.",
    targets: ["Named buttons", "Text input", "Textarea"],
  },
  {
    href: "/forms",
    title: "Forms",
    difficulty: 2,
    description:
      "A realistic form with text inputs, selects, checkboxes, radio buttons, and a submit button. Labels are adjacent to — not inside — elements.",
    targets: ["Input fields", "Select dropdowns", "Checkboxes", "Radio buttons", "Submit button"],
  },
  {
    href: "/icons",
    title: "Icons",
    difficulty: 3,
    description:
      "Small icon-only buttons (~28px) with no text. Model must reason about shape, color, or position. No label to anchor on.",
    targets: ["Edit icon", "Delete icon", "Copy icon", "Share icon", "Pin icon"],
  },
  {
    href: "/modals",
    title: "Modals",
    difficulty: 4,
    description:
      "Buttons that open modal overlays. Target elements appear only after a trigger click. Tests contextual disambiguation (two 'Close' buttons exist simultaneously).",
    targets: ["Trigger button", "Modal close ×", "Modal confirm", "Modal cancel"],
  },
  {
    href: "/density",
    title: "Density",
    difficulty: 5,
    description:
      "48 small, tightly-packed buttons with similar labels (Button 1…48). Requires fine-grained spatial reasoning to distinguish neighbors.",
    targets: ["Specific numbered buttons", "Edge buttons", "Center buttons"],
  },
  {
    href: "/dynamic",
    title: "Dynamic",
    difficulty: 6,
    description:
      "Elements appear and disappear on timers. Tests the wait_for command — model must detect when a target becomes visible, not just where it is.",
    targets: ["Timed button", "Countdown element", "Auto-hiding alert"],
  },
];

const DOTS: Record<number, string> = {
  1: "bg-emerald-500",
  2: "bg-sky-500",
  3: "bg-amber-500",
  4: "bg-orange-500",
  5: "bg-rose-500",
  6: "bg-red-700",
};

export default function HomePage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-3xl font-bold">OpenClaw VNC Click Lab</h1>
      <p className="mt-2 text-slate-400">
        Multi-scenario benchmark surface for vision-based element detection. Each page tests a different
        detection challenge. All elements report exact native screen coordinates via{" "}
        <code className="rounded bg-slate-800 px-1 text-violet-300">GET /api/element-coords</code>.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        {SCENARIOS.map((s) => (
          <Link
            key={s.href}
            href={s.href}
            data-element-id={`home_card_${s.title.toLowerCase().replace(/[^a-z0-9]/g, "_")}`}
            data-element-label={s.title}
            data-element-kind="card-link"
            className="group flex flex-col gap-2 rounded-xl border border-slate-700 bg-slate-900 p-5 hover:border-violet-500 transition"
          >
            <div className="flex items-center gap-3">
              <div className="flex gap-1">
                {Array.from({ length: 6 }).map((_, i) => (
                  <span
                    key={i}
                    className={`h-2 w-2 rounded-full ${i < s.difficulty ? DOTS[s.difficulty] : "bg-slate-700"}`}
                  />
                ))}
              </div>
              <span className="text-xs text-slate-500">Difficulty {s.difficulty}/6</span>
            </div>
            <h2 className="text-lg font-semibold group-hover:text-violet-300 transition">{s.title}</h2>
            <p className="text-sm text-slate-400">{s.description}</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {s.targets.map((t) => (
                <span key={t} className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                  {t}
                </span>
              ))}
            </div>
          </Link>
        ))}
      </div>

      <div className="mt-8 rounded-xl border border-slate-700 bg-slate-900 p-5">
        <h2 className="mb-2 font-semibold">Benchmark API</h2>
        <div className="space-y-2 text-sm text-slate-400">
          <p>
            <code className="text-violet-300">GET /api/element-coords</code> — latest snapshot of all
            visible element native screen coordinates. Refreshes automatically on page load and resize.
            Hit the <span className="text-violet-300">📍 Report Coords</span> button on any page to force
            a fresh snapshot.
          </p>
          <p>
            <code className="text-violet-300">GET /api/vnc-click-log?count=50</code> — last N click events
            with per-click accuracy telemetry (pointer vs target delta in px, native coords).
          </p>
        </div>
      </div>
    </div>
  );
}
