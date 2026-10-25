import type { MonitoringStation } from "@/types";
import { Card } from "@/components/ui/card";
import { Status } from "@/components/ui/status";
import { formatDateTime } from "@/lib/date-time";

export function MonitoringStationCard({
  station,
  associatedPatientNames,
}: {
  station: MonitoringStation;
  associatedPatientNames?: string[];
}) {
  const tone = station.status === "online" ? "healthy" : station.status === "degraded" ? "warning" : "offline";
  const statusLabel = station.status === "online" ? "Connected" : station.status === "degraded" ? "Limited connection" : station.status[0].toUpperCase() + station.status.slice(1);

  return (
    <Card className="p-4">
      <p className="font-medium">{station.name}</p>
      {associatedPatientNames && <p className="mt-1 text-xs text-[var(--color-text-muted)] metric-number">{station.id}</p>}
      <div className="mt-2"><Status label={statusLabel} tone={tone} /></div>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
        <dt className="text-[var(--color-text-muted)]">Wearables</dt>
        <dd>{station.deviceIds.length} assigned</dd>
        <dt className="text-[var(--color-text-muted)]">Last update</dt>
        <dd>{station.lastSeenAt ? formatDateTime(station.lastSeenAt) : "Not available"}</dd>
        {associatedPatientNames && (
          <>
            <dt className="text-[var(--color-text-muted)]">Patients</dt>
            <dd>{associatedPatientNames.length}</dd>
          </>
        )}
      </dl>
      {associatedPatientNames && (
        <p className="mt-3 border-t border-[var(--color-border)] pt-3 text-sm text-[var(--color-text-muted)]">
          {associatedPatientNames.length ? associatedPatientNames.join(", ") : "No registered patients"}
        </p>
      )}
    </Card>
  );
}
