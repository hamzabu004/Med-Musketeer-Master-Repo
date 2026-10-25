import { Card } from "./card";

export function Metric({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">{label}</p>
      <p className="metric-number mt-2 text-2xl font-semibold">{value}</p>
      {detail && <p className="mt-1 text-xs text-[var(--color-text-muted)]">{detail}</p>}
    </Card>
  );
}

export function SectionTitle({ children, actions }: { children: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-2">
      <h3 className="text-base font-semibold">{children}</h3>
      {actions}
    </div>
  );
}
