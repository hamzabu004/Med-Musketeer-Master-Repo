"use client";

import type { Alert } from "@/api/types";
import { useData } from "@/auth/session";
import { useAction } from "@/lib/use-action";

/** The doctor's acknowledge, reloading the screen afterwards. A 409 (already acknowledged, by a
 * colleague or another tab) reloads too, so the screen shows who did. */
export function useAcknowledge(reload: () => void) {
  const { data } = useData();
  const action = useAction();
  async function acknowledge(alert: Alert) {
    await action.run(`ack-${alert.alert_id}`, () => data.care.acknowledge(alert.alert_id), "Alert acknowledged.");
    reload();
  }
  return { acknowledge, busy: action.busy !== null, notice: action.notice };
}
