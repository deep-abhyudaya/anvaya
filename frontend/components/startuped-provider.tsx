"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import {
  flushStartupedEvents,
  trackError,
  trackFormSubmission,
  trackRouteView,
  trackUiInteraction,
} from "@/lib/startuped";

export function StartupedProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const lastRoute = useRef<string | null>(null);

  useEffect(() => {
    if (!pathname || lastRoute.current === pathname) return;
    lastRoute.current = pathname;
    trackRouteView(pathname);
  }, [pathname]);

  useEffect(() => {
    const onClick = (event: MouseEvent) => trackUiInteraction(event.target);
    const onSubmit = (event: SubmitEvent) => {
      if (event.target instanceof HTMLFormElement) trackFormSubmission(event.target);
    };
    const onError = (event: ErrorEvent) => trackError(event.message || "Client error", "window");
    const onRejection = (event: PromiseRejectionEvent) =>
      trackError(String(event.reason || "Unhandled rejection"), "promise");
    const onHidden = () => {
      if (document.visibilityState === "hidden") void flushStartupedEvents();
    };
    const onPageHide = () => void flushStartupedEvents();

    document.addEventListener("click", onClick, { capture: true, passive: true });
    document.addEventListener("submit", onSubmit, { capture: true });
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    document.addEventListener("visibilitychange", onHidden);
    window.addEventListener("pagehide", onPageHide);

    return () => {
      document.removeEventListener("click", onClick, { capture: true });
      document.removeEventListener("submit", onSubmit, { capture: true });
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
      document.removeEventListener("visibilitychange", onHidden);
      window.removeEventListener("pagehide", onPageHide);
    };
  }, []);

  return <>{children}</>;
}
