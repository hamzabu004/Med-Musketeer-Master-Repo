import { shortId } from "@/lib/labels";

/** A UUID shown short, with the full value on hover and for screen readers. */
export function RecordId({ id }: { id: string | null | undefined }) {
  if (!id) return <span className="text-[var(--color-text-muted)]">—</span>;
  return (
    <span className="metric-number font-mono text-xs" title={id}>
      {shortId(id)}
      <span className="sr-only"> ({id})</span>
    </span>
  );
}
