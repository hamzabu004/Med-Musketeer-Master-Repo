"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { ClinicalAlertTable } from "@/components/clinical/clinical-alert-table";
import { PatientTable } from "@/components/clinical/patient-table";
import { MonitoringStationCard } from "@/components/monitoring/monitoring-station-card";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageIntro } from "@/components/ui/page-intro";
import { DoctorPageError, DoctorPageSkeleton } from "./doctor-page-state";
import { useDoctorOverview } from "./use-doctor-overview";

const priorityRank = { attention: 0, offline: 1, unknown: 2, normal: 3 } as const;

export function DoctorDashboard() {
  const { state, retry } = useDoctorOverview();
  if (state.status === "loading") return <DoctorPageSkeleton />;
  if (state.status === "error") return <DoctorPageError message={state.message} onRetry={retry} />;

  const { doctor, patients, devices, stations, alerts, readings, preferences } = state.data;
  const devicesByPatient = new Map(devices.map((device) => [device.patientId, device]));
  const stationsById = new Map(stations.map((station) => [station.id, station]));
  const activeMonitoring = patients.filter((patient) => {
    const device = devicesByPatient.get(patient.id);
    const station = patient.monitoringStationId ? stationsById.get(patient.monitoringStationId) : undefined;
    return device?.status === "online" && station?.status === "online";
  }).length;
  const attentionRequired = patients.filter((patient) => patient.monitoringState !== "normal").length;
  const activeAlerts = alerts.filter((alert) => alert.status === "new" || alert.status === "open").length;
  const attentionAlerts = activeAlerts + attentionRequired;
  const prioritizedPatients = [...patients].sort(
    (a, b) => priorityRank[a.monitoringState] - priorityRank[b.monitoringState],
  );
  const recentAlerts = [...alerts]
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
    .slice(0, 4);
  const patientNames = new Map(patients.map((patient) => [patient.id, patient.displayName]));

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title={`Clinical overview — ${doctor.displayName}`} />

      <Card className="grid divide-y divide-[var(--color-border)] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <Summary label="Registered patients" value={patients.length} />
        <Summary label="Active monitoring" value={activeMonitoring} />
        <Summary label="Alerts requiring attention" value={attentionAlerts} tone={attentionAlerts ? "critical" : undefined} />
      </Card>

      <section aria-labelledby="doctor-alerts-heading" className="min-w-0 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 id="doctor-alerts-heading" className="text-xl font-semibold">Recent Alerts</h3>
          <Link href="/doctor/alerts" className="inline-flex items-center gap-1 text-sm font-medium text-[var(--color-info)] hover:underline">
            View alerts <ArrowRight size={14} aria-hidden />
          </Link>
        </div>
        {recentAlerts.length ? (
          <ClinicalAlertTable
            alerts={recentAlerts}
            patientName={(patientId) => patientNames.get(patientId) ?? "Registered patient"}
            patientHref={(alert) => `/doctor/patients/${alert.patientId}`}
            showClassification
            alertHref={(alert) => `/doctor/alerts/${alert.id}`}
          />
        ) : (
          <EmptyState title="No recent alerts" description="No alerts are available for registered patients." />
        )}
      </section>

      <section aria-labelledby="patient-status-heading" className="min-w-0 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 id="patient-status-heading" className="text-lg font-semibold">Patient Status</h3>
          </div>
          <Link href="/doctor/patients" className="inline-flex items-center gap-1 text-sm font-medium text-[var(--color-info)] hover:underline">
            All patients <ArrowRight size={14} aria-hidden />
          </Link>
        </div>
        {prioritizedPatients.length ? (
          <PatientTable patients={prioritizedPatients} stations={stations} readings={readings} heartRateIntervalSeconds={preferences.heartRateMonitoringIntervalSeconds} />
        ) : (
          <EmptyState title="No registered patients" description="No patients are currently registered to this clinician." />
        )}
      </section>

      <section aria-labelledby="assigned-stations-heading" className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 id="assigned-stations-heading" className="text-lg font-semibold">Assigned Monitoring Stations</h3>
          <Link href="/doctor/monitoring-stations" className="inline-flex items-center gap-1 text-sm font-medium text-[var(--color-info)] hover:underline">
            View stations <ArrowRight size={14} aria-hidden />
          </Link>
        </div>
        {stations.length ? (
          <div className="grid gap-4 lg:grid-cols-2">
            {stations.map((station) => <MonitoringStationCard key={station.id} station={station} />)}
          </div>
        ) : (
          <EmptyState title="No assigned Monitoring Stations" description="No Monitoring Stations are assigned to this clinician." />
        )}
      </section>
    </section>
  );
}

function Summary({ label, value, tone }: { label: string; value: number; tone?: "critical" | "warning" }) {
  const toneClass = tone === "critical" ? "text-[var(--color-critical)]" : tone === "warning" ? "text-[var(--color-warning)]" : "";
  return (
    <div className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">{label}</p>
      <p className={`mt-2 text-2xl font-semibold metric-number ${toneClass}`}>{value}</p>
    </div>
  );
}
