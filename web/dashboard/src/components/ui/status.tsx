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
