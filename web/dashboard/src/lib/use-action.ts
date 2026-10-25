"use client";

import { useCallback, useState } from "react";
import { userMessage } from "@/api/errors";

export type Notice = { tone: "success" | "error"; text: string } | null;

/** Runs a change (create, revoke, …) with a busy flag and the outcome as a notice. Resolves to the
 * change's result, or undefined when it failed (the notice then holds the reason). */
export function useAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);

  const run = useCallback(async <T,>(name: string, change: () => Promise<T>, success?: string): Promise<T | undefined> => {
    setBusy(name);
    setNotice(null);
    try {
      const result = await change();
      if (success) setNotice({ tone: "success", text: success });
      return result;
    } catch (error) {
      setNotice({ tone: "error", text: userMessage(error) });
      return undefined;
    } finally {
      setBusy(null);
    }
  }, []);

  return { busy, notice, setNotice, run };
}
