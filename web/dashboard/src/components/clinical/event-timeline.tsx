import { EmptyState } from "@/components/ui/empty-state";
import { formatDateTime } from "@/lib/date-time";
import type { ECGEvent } from "@/types";

export function EventTimeline({ events }: { events: ECGEvent[] }) {
  if (events.length === 0) {
    return <EmptyState title="No events in this range" description="Choose another time range to review earlier events." />;
  }

  return (
    <ol className="border-l border-[var(--color-border-strong)] pl-5">
      {events.map((event) => (
        <li key={event.id} className="relative pb-5 last:pb-0">
          <span className="absolute -left-[25px] top-1.5 size-2 rounded-full bg-[var(--color-accent)]" aria-hidden />
          <p className="text-sm font-medium">
            {event.classification[0].toUpperCase() + event.classification.slice(1)} ECG event
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-muted)] metric-number">
            {formatDateTime(event.timestamp)} · {event.heartRate == null ? "Heart rate unavailable" : `${event.heartRate} bpm`}
          </p>
        </li>
      ))}
    </ol>
  );
}
