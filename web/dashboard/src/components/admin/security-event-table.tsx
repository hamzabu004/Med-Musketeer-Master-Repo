import type { SecurityEvent } from "@/types";
import Link from "next/link";
import { formatDateTime } from "@/lib/date-time";
import { Status } from "@/components/ui/status";

function tone(value: string) {
  if (value === "critical" || value === "active") return "critical" as const;
  if (value === "warning" || value === "acknowledged") return "warning" as const;
  if (value === "resolved") return "healthy" as const;
  return "info" as const;
}

function labelize(value: string) {
  if (value === "info") return "Normal";
  return value.split("-").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

export function SecurityEventTable({ events, compact = false }: { events: SecurityEvent[]; compact?: boolean }) {
  return (
    <div className="overflow-x-auto rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)]">
      <table className={`w-full ${compact ? "min-w-[900px]" : "min-w-[1280px]"} text-sm`}>
        <thead className="bg-[var(--color-surface-subtle)] text-left text-[var(--color-text-muted)]">
          <tr>
            <th className="px-3 py-2">Time</th>
            <th className="px-3 py-2">Event</th>
            <th className="px-3 py-2">Source</th>
            {!compact && <th className="px-3 py-2">Destination</th>}
            {!compact && <th className="px-3 py-2">Monitoring Station</th>}
            <th className="px-3 py-2">Risk level</th>
            {!compact && <th className="px-3 py-2">Detection</th>}
            <th className="px-3 py-2">Response</th>
            <th className="px-3 py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.id} className="border-t border-[var(--color-border)]">
              <td className="px-3 py-3 metric-number">{formatDateTime(event.timestamp)}</td>
              <td className="px-3 py-3 font-medium"><Link className="text-[var(--color-info)] underline-offset-2 hover:underline" href={`/admin/security/events/${event.id}`}>{event.type.split("-").join(" ")}</Link><span className="block text-xs font-normal text-[var(--color-text-muted)]">{event.id}</span></td>
              <td className="px-3 py-3">{event.source}</td>
              {!compact && <td className="px-3 py-3">{event.destination ?? "Not recorded"}</td>}
              {!compact && <td className="px-3 py-3">{event.monitoringStationId ?? "Not associated"}</td>}
              <td className="px-3 py-3"><Status label={labelize(event.severity)} tone={tone(event.severity)} /></td>
              {!compact && <td className="px-3 py-3">{event.detectionMechanism}</td>}
              <td className="px-3 py-3">{event.response}</td>
              <td className="px-3 py-3"><Status label={labelize(event.status)} tone={tone(event.status)} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
