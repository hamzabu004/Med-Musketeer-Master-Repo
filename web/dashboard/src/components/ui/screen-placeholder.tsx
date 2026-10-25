import { Card } from "./card";

/** A route whose screen is not built yet: its title and what it will show. */
export function ScreenPlaceholder({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
      </div>
      <Card className="p-5">
        <p className="text-sm text-[var(--color-text-muted)]">
          {description ?? "This screen is not built yet."}
        </p>
      </Card>
    </section>
  );
}
