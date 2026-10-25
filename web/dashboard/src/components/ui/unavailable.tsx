import { Card } from "./card";

/** A feature whose cloud endpoints are not built yet (API mode): said plainly, never faked. */
export function Unavailable({ feature, reason }: { feature: string; reason: string }) {
  return (
    <Card className="space-y-1 border-dashed p-5">
      <h3 className="font-semibold">{feature} is not available yet</h3>
      <p className="text-sm text-[var(--color-text-muted)]">{reason}</p>
    </Card>
  );
}
