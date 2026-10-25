import { Card } from "./card";

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <Card className="p-5 text-center">
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mx-auto mt-1 max-w-lg text-sm text-[var(--color-text-muted)]">{description}</p>
    </Card>
  );
}
