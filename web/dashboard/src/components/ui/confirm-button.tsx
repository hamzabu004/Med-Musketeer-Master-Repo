"use client";

import { useId, useRef } from "react";
import { Button } from "./button";

/** A button that asks before an action that is hard to undo, saying what will happen. */
export function ConfirmButton({
  label,
  title,
  consequences,
  confirmLabel,
  onConfirm,
  variant = "secondary",
  disabled,
}: {
  label: string;
  title: string;
  consequences: string[];
  confirmLabel?: string;
  onConfirm: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  return (
    <>
      <Button type="button" variant={variant} disabled={disabled} onClick={() => dialog.current?.showModal()}>
        {label}
      </Button>
      <dialog
        ref={dialog}
        className="m-auto w-[min(28rem,calc(100vw-2rem))] rounded-[var(--radius-md)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] p-5 text-[var(--color-text)] backdrop:bg-[var(--color-overlay)]"
        aria-labelledby={titleId}
      >
        <h2 id={titleId} className="font-semibold">
          {title}
        </h2>
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-[var(--color-text-muted)]">
          {consequences.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <form method="dialog" className="mt-5 flex justify-end gap-2">
          <Button type="submit" variant="secondary">
            Cancel
          </Button>
          <Button
            type="button"
            variant={variant === "secondary" ? "primary" : variant}
            onClick={() => {
              dialog.current?.close();
              onConfirm();
            }}
          >
            {confirmLabel ?? label}
          </Button>
        </form>
      </dialog>
    </>
  );
}
