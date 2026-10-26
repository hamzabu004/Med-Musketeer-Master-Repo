"use client";

import { useEffect } from "react";

/** Polls while the page is visible: calls `refresh` every `ms`, and once when the page becomes
 * visible again. Stands in for the alert push (capability "alertStream") until the cloud has it. */
export function usePolling(refresh: () => void, ms: number) {
  useEffect(() => {
    const tick = () => {
      if (document.visibilityState === "visible") refresh();
    };
    const timer = window.setInterval(tick, ms);
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [refresh, ms]);
}

/** How often alert screens re-read the alerts while there is no push. */
export const ALERT_POLL_MS = 15_000;
