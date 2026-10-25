"use client";

import { useState } from "react";
import { ClinicalAlertTable } from "@/components/clinical/clinical-alert-table";
import { EmptyState } from "@/components/ui/empty-state";
import { LabeledSelect } from "@/components/ui/labeled-select";
import { PageIntro } from "@/components/ui/page-intro";
import type { ClinicalAlert } from "@/types";
import { DoctorPageError, DoctorPageSkeleton } from "./doctor-page-state";
import { useDoctorOverview } from "./use-doctor-overview";

type SeverityFilter = "all" | ClinicalAlert["severity"];
type StatusFilter = "all" | ClinicalAlert["status"];

export function DoctorAlerts() {
  const { state, retry } = useDoctorOverview();
  const [patientId, setPatientId] = useState("all");
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");

  if (state.status === "loading") return <DoctorPageSkeleton />;
  if (state.status === "error") return <DoctorPageError message={state.message} onRetry={retry} />;

  const patientNames = new Map(state.data.patients.map((patient) => [patient.id, patient.displayName]));
  const alerts = state.data.alerts
    .filter((alert) => patientId === "all" || alert.patientId === patientId)
    .filter((alert) => severity === "all" || alert.severity === severity)
    .filter((alert) => status === "all" || alert.status === status)
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Clinical Alerts" description="Alerts from patients assigned to your clinician profile." />

      <div className="grid gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:grid-cols-3">
        <LabeledSelect label="Patient" value={patientId} onChange={(event) => setPatientId(event.target.value)}>
          <option value="all">All registered patients</option>
          {state.data.patients.map((patient) => <option key={patient.id} value={patient.id}>{patient.displayName}</option>)}
        </LabeledSelect>
        <LabeledSelect label="Alert level" value={severity} onChange={(event) => setSeverity(event.target.value as SeverityFilter)}>
          <option value="all">All levels</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Normal</option>
        </LabeledSelect>
        <LabeledSelect label="Acknowledgement status" value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)}>
          <option value="all">All statuses</option>
          <option value="new">New</option>
          <option value="open">Open</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
          <option value="read">Read</option>
        </LabeledSelect>
      </div>

      {alerts.length ? (
        <ClinicalAlertTable
          alerts={alerts}
          patientName={(id) => patientNames.get(id) ?? "Registered patient"}
          patientHref={(alert) => `/doctor/patients/${alert.patientId}`}
          showClassification
          alertHref={(alert) => `/doctor/alerts/${alert.id}`}
        />
      ) : (
        <EmptyState title="No matching clinical alerts" description="Adjust the patient, alert level, or status filter." />
      )}
    </section>
  );
}
