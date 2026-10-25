import { Card } from "./card";

export function ScreenPlaceholder({
  title,
}: {
  title: string;
  description?: string;
}) {
  return (
    <section className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      </div>
      <Card className="p-5">
        <p className="text-sm text-[var(--color-text-muted)]">
          Route scaffold ready.
        </p>
      </Card>
    </section>
  );
}
