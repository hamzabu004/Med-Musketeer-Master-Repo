import Link from "next/link";
import { formatDateTime } from "@/lib/date-time";
import type { HeartRateReading, MonitoringStation, Patient } from "@/types";
import { Status, type StatusTone } from "@/components/ui/status";

const monitoringLabels: Record<Patient["monitoringState"], string> = {
  normal: "Monitoring active",
  attention: "Attention required",
  offline: "Monitoring offline",
  unknown: "Status unknown",
};

const monitoringTones: Record<Patient["monitoringState"], StatusTone> = {
  normal: "healthy",
  attention: "critical",
  offline: "warning",
  unknown: "offline",
};

export function PatientTable({
  patients,
  stations,
  readings = [],
  heartRateIntervalSeconds,
}: {
  patients: Patient[];
  stations: MonitoringStation[];
  readings?: HeartRateReading[];
  heartRateIntervalSeconds?: number;
}) {
  const stationNames = new Map(stations.map((station) => [station.id, station.name]));
  const latestReadingByPatient = new Map<string, HeartRateReading>();
  for (const reading of readings) {
    const previous = latestReadingByPatient.get(reading.patientId);
    if (!previous || Date.parse(reading.timestamp) > Date.parse(previous.timestamp)) {
      latestReadingByPatient.set(reading.patientId, reading);
    }
  }

  return (
    <div className="overflow-x-auto rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)]">
      <table className="w-full min-w-[1100px] border-collapse text-sm" aria-label="Registered patients">
        <thead className="bg-[var(--color-surface-subtle)] text-left text-[var(--color-text-muted)]">
          <tr>
            <th className="px-3 py-2 font-medium">Patient</th>
            <th className="px-3 py-2 font-medium">Monitoring state</th>
            <th className="px-3 py-2 text-right font-medium">Latest heart rate</th>
            <th className="px-3 py-2 font-medium">Reading time</th>
            <th className="px-3 py-2 font-medium">Freshness</th>
            <th className="px-3 py-2 font-medium">ECG result</th>
            <th className="px-3 py-2 font-medium">Monitoring Station</th>
          </tr>
        </thead>
        <tbody>
          {patients.map((patient) => {
            const classificationTone = patient.ecgClassification === "normal" ? "healthy" : patient.ecgClassification === "abnormal" ? "critical" : "offline";
            const latestReading = latestReadingByPatient.get(patient.id);
            const ageSeconds = latestReading ? Math.floor((Date.now() - Date.parse(latestReading.timestamp)) / 1000) : null;
            const stale = ageSeconds == null || (heartRateIntervalSeconds ? ageSeconds > heartRateIntervalSeconds * 2 : false);
            return (
              <tr key={patient.id} className="border-t border-[var(--color-border)]">
                <td className={`border-l-2 px-3 py-3 font-medium ${patient.monitoringState === "attention" ? "border-l-[var(--color-critical)]" : patient.monitoringState === "offline" ? "border-l-[var(--color-warning)]" : "border-l-transparent"}`}>
                  <Link href={`/doctor/patients/${patient.id}`} className="text-[var(--color-info)] underline-offset-2 hover:underline">
                    {patient.displayName}
                  </Link>
                </td>
                <td className="px-3 py-3">
                  <Status label={monitoringLabels[patient.monitoringState]} tone={monitoringTones[patient.monitoringState]} />
                </td>
                <td className="px-3 py-3 text-right metric-number">{latestReading ? `${latestReading.bpm} bpm` : patient.currentHeartRate == null ? "—" : `${patient.currentHeartRate} bpm`}</td>
                <td className="px-3 py-3 metric-number">{latestReading ? formatDateTime(latestReading.timestamp) : formatDateTime(patient.lastUpdatedAt)}</td>
                <td className="px-3 py-3">
                  <Status label={stale ? "Stale" : "Current"} tone={stale ? "warning" : "healthy"} />
                </td>
                <td className="px-3 py-3">
                  <Status label={patient.ecgClassification[0].toUpperCase() + patient.ecgClassification.slice(1)} tone={classificationTone} />
                </td>
                <td className="px-3 py-3">{patient.monitoringStationId ? stationNames.get(patient.monitoringStationId) ?? patient.monitoringStationId : "Not assigned"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
