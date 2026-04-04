import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "OpenClaw VNC Click Lab",
  description: "Multi-scenario test surface for vision-based VNC element detection benchmarks",
};

const NAV = [
  { href: "/", label: "Home" },
  { href: "/vnc-click-lab", label: "Grid (Easy)" },
  { href: "/forms", label: "Forms" },
  { href: "/icons", label: "Icons" },
  { href: "/modals", label: "Modals" },
  { href: "/density", label: "Density" },
  { href: "/dynamic", label: "Dynamic" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-950 text-white">
        <nav className="flex items-center gap-1 border-b border-slate-800 bg-slate-900 px-4 py-2 text-xs">
          <span className="mr-3 font-bold text-violet-400">VNC Lab</span>
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              data-element-id={`nav_${n.label.toLowerCase().replace(/[^a-z0-9]/g, "_")}`}
              data-element-label={n.label}
              data-element-kind="nav-link"
              className="rounded px-2 py-1 text-slate-300 hover:bg-slate-700 hover:text-white transition"
            >
              {n.label}
            </Link>
          ))}
        </nav>
        {children}
      </body>
    </html>
  );
}
