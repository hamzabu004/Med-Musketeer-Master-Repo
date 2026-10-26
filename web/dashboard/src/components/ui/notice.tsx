import type { Notice as NoticeValue } from "@/lib/use-action";
import { cn } from "@/lib/cn";

/** The outcome of a change: announced to screen readers, red for a refusal. */
export function Notice({ notice }: { notice: NoticeValue }) {
  if (!notice) return null;
  return (
    <p
      role={notice.tone === "error" ? "alert" : "status"}
      className={cn(
        "border-l-2 px-3 py-2 text-sm",
        notice.tone === "error"
          ? "border-[var(--color-critical)] bg-[var(--color-surface)] text-[var(--color-critical)]"
          : "border-[var(--color-accent)] bg-[var(--color-accent-soft)]",
      )}
    >
      {notice.text}
    </p>
  );
}
