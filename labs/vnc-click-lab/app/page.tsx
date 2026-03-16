import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center p-6">
      <div className="max-w-2xl text-center space-y-4">
        <h1 className="text-3xl font-bold">OpenClaw VNC Click Lab</h1>
        <p className="text-slate-300">
          Standalone test surface for click accuracy, typing, key propagation, and coordinate calibration.
        </p>
        <Link
          href="/vnc-click-lab"
          className="inline-block rounded bg-emerald-600 hover:bg-emerald-500 px-4 py-2 font-semibold"
        >
          Open /vnc-click-lab
        </Link>
      </div>
    </main>
  );
}
