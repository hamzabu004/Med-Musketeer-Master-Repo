"use client";

import { useState } from "react";
import { EmptyState } from "@/components/ui/empty-state";
import { LabeledSelect } from "@/components/ui/labeled-select";
import { PageIntro } from "@/components/ui/page-intro";
import { Status, type StatusTone } from "@/components/ui/status";
import { filterByRange, formatDateTime, type TimeRange } from "@/lib/date-time";
import type { ECGClassification, Severity } from "@/types";
import { DoctorPageError, DoctorPageSkeleton } from "./doctor-page-state";
import { useDoctorOverview } from "./use-doctor-overview";

type SeverityFilter = "all" | Severity;
type ClassificationFilter = "all" | ECGClassification;

const severityTones: Record<Severity, StatusTone> = {
  info: "healthy",
  warning: "warning",
  critical: "critical",
};

const severityLabels: Record<Severity, string> = {
  info: "Normal",
  warning: "Warning",
  critical: "Critical",
};

export function DoctorHistory() {
  const { state, retry } = useDoctorOverview();
  const [patientId, setPatientId] = useState("all");
  const [range, setRange] = useState<TimeRange>("7d");
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [classification, setClassification] = useState<ClassificationFilter>("all");

  if (state.status === "loading") return <DoctorPageSkeleton />;
  if (state.status === "error") return <DoctorPageError message={state.message} onRetry={retry} />;

  const patientNames = new Map(state.data.patients.map((patient) => [patient.id, patient.displayName]));
  const alertByEvent = new Map(
    state.data.alerts.filter((alert) => alert.eventId).map((alert) => [alert.eventId, alert]),
  );
  const rangedEvents = filterByRange(state.data.events, range, (event) => event.timestamp);
  const events = rangedEvents
    .map((event) => ({ event, severity: alertByEvent.get(event.id)?.severity ?? ("info" as const) }))
    .filter((row) => patientId === "all" || row.event.patientId === patientId)
    .filter((row) => severity === "all" || row.severity === severity)
    .filter((row) => classification === "all" || row.event.classification === classification)
    .sort((a, b) => Date.parse(b.event.timestamp) - Date.parse(a.event.timestamp));

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Patient History" description="Aggregated event history for registered patients only." />

      <div className="grid gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:grid-cols-2 xl:grid-cols-4">
        <LabeledSelect label="Patient" value={patientId} onChange={(event) => setPatientId(event.target.value)}>
          <option value="all">All registered patients</option>
          {state.data.patients.map((patient) => <option key={patient.id} value={patient.id}>{patient.displayName}</option>)}
        </LabeledSelect>
        <LabeledSelect label="Date range" value={range} onChange={(event) => setRange(event.target.value as TimeRange)}>
          <option value="24h">Last 24 hours</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </LabeledSelect>
        <LabeledSelect label="Alert level" value={severity} onChange={(event) => setSeverity(event.target.value as SeverityFilter)}>
          <option value="all">All levels</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Normal</option>
        </LabeledSelect>
        <LabeledSelect label="ECG classification" value={classification} onChange={(event) => setClassification(event.target.value as ClassificationFilter)}>
          <option value="all">All classifications</option>
          <option value="normal">Normal</option>
          <option value="abnormal">Abnormal</option>
          <option value="unclassified">Unclassified</option>
        </LabeledSelect>
      </div>

      {events.length ? (
        <div className="overflow-x-auto rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)]">
          <table className="w-full min-w-[800px] border-collapse text-sm" aria-label="Registered-patient history">
            <thead className="bg-[var(--color-surface-subtle)] text-left text-[var(--color-text-muted)]">
              <tr>
                <th className="px-3 py-2 font-medium">Time</th>
                <th className="px-3 py-2 font-medium">Patient</th>
                <th className="px-3 py-2 font-medium">Event</th>
                <th className="px-3 py-2 font-medium">Alert level</th>
                <th className="px-3 py-2 font-medium">Classification</th>
                <th className="px-3 py-2 text-right font-medium">Heart rate</th>
              </tr>
            </thead>
            <tbody>
              {events.map(({ event, severity: eventSeverity }) => (
                <tr key={event.id} className="border-t border-[var(--color-border)]">
                  <td className="px-3 py-3 metric-number">{formatDateTime(event.timestamp)}</td>
                  <td className="px-3 py-3 font-medium">{patientNames.get(event.patientId) ?? "Registered patient"}</td>
                  <td className="px-3 py-3 metric-number">{event.id}</td>
                  <td className="px-3 py-3"><Status label={severityLabels[eventSeverity]} tone={severityTones[eventSeverity]} /></td>
                  <td className="px-3 py-3 capitalize">{event.classification}</td>
                  <td className="px-3 py-3 text-right metric-number">{event.heartRate == null ? "—" : `${event.heartRate} bpm`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState title="No matching patient history" description="Adjust the patient, range, alert level, or classification filter." />
      )}
    </section>
  );
}
