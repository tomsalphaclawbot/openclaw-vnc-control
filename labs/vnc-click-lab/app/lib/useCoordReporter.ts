/**
 * useCoordReporter
 *
 * Shared hook: on mount + resize, queries all [data-element-id] elements on
 * the page, computes their exact native screen coordinates via
 * getBoundingClientRect() + window.screenX/Y + devicePixelRatio, and POSTs
 * a snapshot to /api/element-coords.
 *
 * Benchmark runner can GET /api/element-coords at any time for ground truth.
 */
"use client";

import { useCallback, useEffect, useState } from "react";

function round4(v: number) {
  return Number(v.toFixed(4));
}

export function useCoordReporter() {
  const [coordStatus, setCoordStatus] = useState<string>("Coords not yet reported");

  const reportCoords = useCallback(async () => {
    const dpr = window.devicePixelRatio || 1;
    const chromeTop = window.outerHeight - window.innerHeight;

    const windowMetrics = {
      screenX: round4(window.screenX),
      screenY: round4(window.screenY),
      innerWidth: round4(window.innerWidth),
      innerHeight: round4(window.innerHeight),
      outerWidth: round4(window.outerWidth),
      outerHeight: round4(window.outerHeight),
      devicePixelRatio: round4(dpr),
      scrollX: round4(window.scrollX),
      scrollY: round4(window.scrollY),
    };

    const elements: object[] = [];

    document.querySelectorAll<HTMLElement>("[data-element-id]").forEach((el) => {
      const r = el.getBoundingClientRect();
      // Skip elements with zero size (hidden/unmounted)
      if (r.width === 0 && r.height === 0) return;

      const centerClientX = r.left + r.width / 2;
      const centerClientY = r.top + r.height / 2;
      const cssX = window.screenX + centerClientX;
      const cssY = window.screenY + chromeTop + centerClientY;

      elements.push({
        id: el.dataset.elementId,
        label: el.dataset.elementLabel ?? el.textContent?.trim().slice(0, 80) ?? el.id ?? "unknown",
        kind: el.dataset.elementKind ?? el.tagName.toLowerCase(),
        rect: {
          top: round4(r.top),
          left: round4(r.left),
          right: round4(r.right),
          bottom: round4(r.bottom),
          width: round4(r.width),
          height: round4(r.height),
        },
        center: {
          clientX: round4(centerClientX),
          clientY: round4(centerClientY),
        },
        screen: {
          cssX: round4(cssX),
          cssY: round4(cssY),
          nativeX: round4(cssX * dpr),
          nativeY: round4(cssY * dpr),
        },
      });
    });

    try {
      await fetch("/api/element-coords", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          capturedAt: new Date().toISOString(),
          windowMetrics,
          elements,
        }),
      });
      setCoordStatus(
        `📍 ${elements.length} elements reported at ${new Date().toLocaleTimeString()}`
      );
    } catch {
      setCoordStatus("⚠️ Coord report failed");
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void reportCoords(), 300);
    const onResize = () => void reportCoords();
    window.addEventListener("resize", onResize);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("resize", onResize);
    };
  }, [reportCoords]);

  return { reportCoords, coordStatus };
}
