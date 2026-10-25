import { Card } from "@/components/ui/card";
import { Status, type StatusTone } from "@/components/ui/status";

export function Metric({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return <Card className="p-4"><p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">{label}</p><p className="metric-number mt-2 text-2xl font-semibold">{value}</p><p className="mt-1 text-xs text-[var(--color-text-muted)]">{detail}</p></Card>;
}

export function SectionTitle({ children }: { children: React.ReactNode; description?: string }) {
  return <div><h3 className="text-base font-semibold">{children}</h3></div>;
}

export function statusTone(value: string): StatusTone {
  if (["online", "active", "resolved", "healthy"].includes(value)) return "healthy";
  if (["degraded", "warning", "acknowledged", "pending", "needs-review"].includes(value)) return "warning";
  if (["critical", "disabled"].includes(value)) return "critical";
  if (["offline"].includes(value)) return "offline";
  return "info";
}

export function LabeledStatus({ value }: { value: string }) {
  return <Status label={labelize(value)} tone={statusTone(value)} />;
}

export function labelize(value: string) {
  if (value === "degraded") return "Limited Connection";
  return value.split("-").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

export const inputClass = "mt-1 h-9 w-full rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-2 text-sm";
export const tableWrapClass = "overflow-x-auto rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)]";
export const tableClass = "w-full min-w-[760px] text-sm";
export const thClass = "px-3 py-2 text-left font-medium";
export const tdClass = "px-3 py-3 align-top";
