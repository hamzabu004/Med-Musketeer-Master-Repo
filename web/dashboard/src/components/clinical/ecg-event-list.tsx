import type { ECGEvent } from "@/types";
import { formatDateTime } from "@/lib/date-time";
import { Status } from "@/components/ui/status";

export function ECGEventList({ events }: { events: ECGEvent[] }) {
  return (
    <div className="overflow-x-auto rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)]">
      <table className="w-full min-w-[620px] border-collapse text-sm" aria-label="ECG event history">
        <thead className="bg-[var(--color-surface-subtle)] text-left text-[var(--color-text-muted)]">
          <tr>
            <th className="px-3 py-2 font-medium">Time</th>
            <th className="px-3 py-2 font-medium">ECG result</th>
            <th className="px-3 py-2 font-medium">Reason</th>
            <th className="px-3 py-2 text-right font-medium">Heart rate</th>
            <th className="px-3 py-2 font-medium">Alert status</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => {
            const tone = event.classification === "normal" ? "healthy" : event.classification === "abnormal" ? "critical" : "offline";
            return (
              <tr key={event.id} className="border-t border-[var(--color-border)]">
                <td className="px-3 py-3 metric-number">{formatDateTime(event.timestamp)}</td>
                <td className="px-3 py-3">
                  <Status label={event.classification[0].toUpperCase() + event.classification.slice(1)} tone={tone} />
                </td>
                <td className="px-3 py-3">{event.acquisitionReason ?? "Monitoring event"}</td>
                <td className="px-3 py-3 text-right metric-number">{event.heartRate == null ? "—" : `${event.heartRate} bpm`}</td>
                <td className="px-3 py-3 capitalize">{event.alertStatus}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
