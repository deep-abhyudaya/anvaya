"use client";

import { useEffect } from "react";

export function useTileAnchor() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash.replace("#", "");
    if (!hash) return;

    const el = document.getElementById(hash);
    if (!el) return;

    el.scrollIntoView({ behavior: "smooth", block: "start" });

    const panel = el.querySelector(".panel, [class*='bg-canvas-panel']") as HTMLElement | null;
    const target = panel || el;
    target.classList.add(
      "ring-2",
      "ring-accent",
      "ring-offset-2",
      "ring-offset-canvas"
    );

    const t = setTimeout(() => {
      target.classList.remove(
        "ring-2",
        "ring-accent",
        "ring-offset-2",
        "ring-offset-canvas"
      );
    }, 1400);

    return () => clearTimeout(t);
  }, []);
}
