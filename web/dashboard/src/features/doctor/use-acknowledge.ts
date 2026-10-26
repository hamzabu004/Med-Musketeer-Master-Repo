"use client";

import { useState } from "react";
import type { Alert } from "@/api/types";
import { ApiError, userMessage } from "@/api/errors";
import { useData } from "@/auth/session";
import { useAction } from "@/lib/use-action";

/** The doctor's acknowledge, reloading the screen afterwards. A 409 (acknowledged by a colleague or
 * another tab) reloads too, so the screen shows who did. An alert stays `pending` from the click
 * until the reloaded list shows it acknowledged, so it cannot be acknowledged twice in between. */
export function useAcknowledge(reload: () => void) {
  const { data } = useData();
  const action = useAction();
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());

  async function acknowledge(alert: Alert) {
    setPending((ids) => new Set(ids).add(alert.alert_id));
    try {
      await data.care.acknowledge(alert.alert_id);
      action.setNotice({ tone: "success", text: "Alert acknowledged." });
    } catch (error) {
      action.setNotice({ tone: "error", text: userMessage(error) });
      // Only a refusal other than "already acknowledged" leaves the alert open to try again.
      if (!(error instanceof ApiError && error.status === 409)) {
        setPending((ids) => {
          const next = new Set(ids);
          next.delete(alert.alert_id);
          return next;
        });
      }
    }
    reload();
  }

  return { acknowledge, isPending: (alert: Alert) => pending.has(alert.alert_id), notice: action.notice };
}
