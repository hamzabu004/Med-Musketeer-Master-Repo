"use client";

import Link from "next/link";
import { ArrowLeft, History } from "lucide-react";
import { ClinicalAlertTable } from "@/components/clinical/clinical-alert-table";
import { ECGRequestPanel } from "@/components/clinical/ecg-request-panel";
import { PatientMonitoringPanel } from "@/components/clinical/patient-monitoring-panel";
import { EmptyState } from "@/components/ui/empty-state";
import { PageIntro } from "@/components/ui/page-intro";
import { Status, type StatusTone } from "@/components/ui/status";
import type { Patient } from "@/types";
import { DoctorPageError, DoctorPageSkeleton } from "./doctor-page-state";
import { useDoctorOverview } from "./use-doctor-overview";

const stateLabels: Record<Patient["monitoringState"], string> = {
  normal: "Monitoring active",
  attention: "Attention required",
  offline: "Monitoring offline",
  unknown: "Status unknown",
};
const stateTones: Record<Patient["monitoringState"], StatusTone> = {
  normal: "healthy",
  attention: "critical",
  offline: "warning",
  unknown: "offline",
};

export function DoctorPatientProfile({ patientId }: { patientId: string }) {
  const { state, retry } = useDoctorOverview();
  if (state.status === "loading") return <DoctorPageSkeleton />;
  if (state.status === "error") return <DoctorPageError message={state.message} onRetry={retry} />;

  const data = state.data;
  const patient = data.patients.find((item) => item.id === patientId);
  if (!patient) {
    return (
      <section className="mx-auto max-w-5xl space-y-5">
        <Link href="/doctor/patients" className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-info)] hover:underline">
          <ArrowLeft size={15} aria-hidden /> Back to patients
        </Link>
        <EmptyState title="Patient not found" description="This patient is not assigned to your clinician profile." />
      </section>
    );
  }

  const device = data.devices.find((item) => item.id === patient.deviceId) ?? null;
  const station = data.stations.find((item) => item.id === patient.monitoringStationId) ?? null;
  const events = data.events.filter((event) => event.patientId === patient.id);
  const readings = data.readings.filter((reading) => reading.patientId === patient.id);
  const ecgRequests = data.ecgRequests.filter((request) => request.patientId === patient.id);
  const alerts = data.alerts
    .filter((alert) => alert.patientId === patient.id)
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <Link href="/doctor/patients" className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-info)] hover:underline">
        <ArrowLeft size={15} aria-hidden /> Back to patients
      </Link>
      <PageIntro
        title={patient.displayName}
        description="Registered-patient monitoring profile using simulated data."
        actions={
          <Link
            href={`/doctor/patients/${patient.id}/history`}
            className="inline-flex h-9 items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 text-sm font-medium hover:bg-[var(--color-surface-subtle)]"
          >
            <History size={16} aria-hidden /> Patient history
          </Link>
        }
      />
      <Status label={stateLabels[patient.monitoringState]} tone={stateTones[patient.monitoringState]} />

      <ECGRequestPanel
        organizationId={data.session.organizationId}
        patient={patient}
        requestedByUserId={data.session.userId}
        requests={ecgRequests}
        events={events}
        onChanged={retry}
      />

      <PatientMonitoringPanel
        patient={patient}
        clinician={data.doctor}
        device={device}
        station={station}
        events={events}
        readings={readings}
        preferences={data.preferences}
        showLiveEcg={false}
      />

      <section aria-labelledby="patient-alerts-heading" className="min-w-0 space-y-3">
        <h3 id="patient-alerts-heading" className="text-lg font-semibold">Recent clinical alerts</h3>
        {alerts.length ? (
          <ClinicalAlertTable
            alerts={alerts.slice(0, 5)}
            showClassification
            alertHref={(alert) => `/doctor/alerts/${alert.id}`}
          />
        ) : (
          <EmptyState title="No recent alerts" description="No clinical alerts are available for this patient." />
        )}
      </section>
    </section>
  );
}
