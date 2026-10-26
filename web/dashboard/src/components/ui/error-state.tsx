import { AlertTriangle } from "lucide-react";
import { Button } from "./button";
import { Card } from "./card";

export function ErrorState({
  title,
  description,
  onRetry,
}: {
  title: string;
  description: string;
  onRetry?: () => void;
}) {
  return (
    <Card className="border-[var(--color-critical)] p-5">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 shrink-0 text-[var(--color-critical)]" size={18} aria-hidden />
        <div>
          <h2 className="font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">{description}</p>
          {onRetry && (
            <Button type="button" variant="secondary" className="mt-4" onClick={onRetry}>
              Try again
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
