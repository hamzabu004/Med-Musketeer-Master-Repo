import type { Patient } from "@/types";
import { Card } from "@/components/ui/card";
import { Status } from "@/components/ui/status";

export function PatientSummaryCard({ patient }: { patient: Patient }) {
  const tone =
    patient.monitoringState === "normal"
      ? "healthy"
      : patient.monitoringState === "attention"
        ? "critical"
        : "offline";

  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-medium">{patient.displayName}</p>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            ECG: {patient.ecgClassification}
          </p>
        </div>
        <Status label={patient.monitoringState} tone={tone} />
      </div>
      <div className="mt-4 text-3xl font-semibold metric-number">
        {patient.currentHeartRate ?? "—"}
        <span className="ml-1 text-sm font-normal text-[var(--color-text-muted)]">BPM</span>
      </div>
    </Card>
  );
}
