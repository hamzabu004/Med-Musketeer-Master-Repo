"use client";

import { useEffect } from "react";
import type { Alert } from "@/api/types";

/** The "dashboard render" checkpoint of the latency methodology (stack.md, "Methodology
 * requirement"): a performance mark when an alert is first drawn on this page load, carrying its id
 * and creation time. Captured for measurement only; never used for any decision. */
export const RENDER_MARK = "mm:dashboard-render";
const marked = new Set<string>();

export function markRendered(alerts: readonly Pick<Alert, "alert_id" | "created_at">[]) {
  if (typeof performance === "undefined" || typeof performance.mark !== "function") return;
  for (const alert of alerts) {
    if (marked.has(alert.alert_id)) continue;
    marked.add(alert.alert_id);
    performance.mark(RENDER_MARK, { detail: { alert_id: alert.alert_id, created_at: alert.created_at } });
  }
}

export function useRenderMarks(alerts: readonly Alert[] | null) {
  useEffect(() => {
    if (alerts) markRendered(alerts);
  }, [alerts]);
}
