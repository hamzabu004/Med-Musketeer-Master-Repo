"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Button } from "./button";

/** An invite code the API returns once: shown until the admin confirms they passed it on. */
export function OneTimeCode({ code, recipient, onDone }: { code: string; recipient: string; onDone: () => void }) {
  const [copy, setCopy] = useState<"idle" | "copied" | "failed">("idle");
  return (
    <div role="status" className="space-y-3 rounded-[var(--radius-md)] border border-[var(--color-warning)] bg-[var(--color-surface)] p-4">
      <p className="text-sm">
        Invite code for <strong>{recipient}</strong>. It is shown <strong>only now</strong>: give it to them before closing this.
        They enter it at sign-in with their e-mail address, then choose a password.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <code className="metric-number rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface-subtle)] px-3 py-1.5 text-lg tracking-[0.2em]">
          {code}
        </code>
        <Button
          type="button"
          variant="secondary"
          onClick={async () => {
            // The clipboard exists only on https (or localhost) and may be refused: say so rather than claim it.
            try {
              if (!navigator.clipboard) throw new Error("no clipboard");
              await navigator.clipboard.writeText(code);
              setCopy("copied");
            } catch {
              setCopy("failed");
            }
          }}
        >
          {copy === "copied" ? <Check size={16} aria-hidden /> : <Copy size={16} aria-hidden />}
          {copy === "copied" ? "Copied" : "Copy"}
        </Button>
      </div>
      {copy === "failed" && <p className="text-sm text-[var(--color-critical)]">Copying is not available here. Write the code down before closing this.</p>}
      <Button type="button" onClick={onDone}>
        I have passed it on
      </Button>
    </div>
  );
}
