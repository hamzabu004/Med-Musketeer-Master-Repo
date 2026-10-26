import { cn } from "@/lib/cn";

const tones = {
  healthy: "text-[var(--color-healthy)]",
  warning: "text-[var(--color-warning)]",
  critical: "text-[var(--color-critical)]",
  offline: "text-[var(--color-offline)]",
  info: "text-[var(--color-info)]",
};

export type StatusTone = keyof typeof tones;

export function Status({
  label,
  tone,
}: {
  label: string;
  tone: StatusTone;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-sm font-medium", tones[tone])}>
      <span className="size-2 rounded-full bg-current" aria-hidden />
      <span>{label}</span>
    </span>
  );
}

/** The tone of a status code from the API (device, organisation, account, credential, alert). */
export function statusTone(value: string | null | undefined): StatusTone {
  switch (value) {
    case "active":
    case "acked":
    case "applied":
    case "no_threat":
      return "healthy";
    case "pending":
    case "suspended":
    case "sent":
    case "detected":
      return "warning";
    case "revoked":
    case "disabled":
    case "blocked":
    case "failed":
      return "critical";
    case "expired":
      return "offline";
    default:
      return "info";
  }
}
