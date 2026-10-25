import Link from "next/link";
import type { ClinicalAlert } from "@/types";
import { formatDateTime } from "@/lib/date-time";
import { Status, type StatusTone } from "@/components/ui/status";

const severityTone: Record<ClinicalAlert["severity"], StatusTone> = {
  info: "healthy",
  warning: "warning",
  critical: "critical",
};

const severityLabels: Record<ClinicalAlert["severity"], string> = {
  info: "Normal",
  warning: "Warning",
  critical: "Critical",
};

export function ClinicalAlertTable({
  alerts,
  alertHref,
  patientHref,
  patientName,
  showClassification = false,
}: {
  alerts: ClinicalAlert[];
  alertHref?: (alert: ClinicalAlert) => string;
  patientHref?: (alert: ClinicalAlert) => string;
  patientName?: (patientId: string) => string;
  showClassification?: boolean;
}) {
  return (
    <div className="overflow-x-auto rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)]">
      <table className="w-full min-w-[680px] border-collapse text-sm" aria-label="Clinical alerts">
        <thead className="bg-[var(--color-surface-subtle)] text-left text-[var(--color-text-muted)]">
          <tr>
            {patientName && <th className="px-3 py-2 font-medium">Patient</th>}
            <th className="px-3 py-2 font-medium">Alert level</th>
            <th className="px-3 py-2 font-medium">Event</th>
            <th className="px-3 py-2 font-medium">Time</th>
            {showClassification && <th className="px-3 py-2 font-medium">ECG result</th>}
            <th className="px-3 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => (
            <tr key={alert.id} className="border-t border-[var(--color-border)]">
              {patientName && (
                <td className="px-3 py-3 font-medium">
                  {patientHref ? (
                    <Link className="text-[var(--color-info)] underline-offset-2 hover:underline" href={patientHref(alert)}>
                      {patientName(alert.patientId)}
                    </Link>
                  ) : patientName(alert.patientId)}
                </td>
              )}
              <td className="px-3 py-3"><Status label={severityLabels[alert.severity]} tone={severityTone[alert.severity]} /></td>
              <td className="px-3 py-3 font-medium">
                {alertHref ? (
                  <Link className="text-[var(--color-info)] underline-offset-2 hover:underline" href={alertHref(alert)}>
                    {alert.title}
                  </Link>
                ) : alert.title}
              </td>
              <td className="px-3 py-3 metric-number">{formatDateTime(alert.timestamp)}</td>
              {showClassification && (
                <td className="px-3 py-3 capitalize">{alert.ecgClassification ?? "normal"}</td>
              )}
              <td className="px-3 py-3 capitalize">{alert.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
