"use client";

import { useState } from "react";
import { ClinicalAlertTable } from "@/components/clinical/clinical-alert-table";
import { EmptyState } from "@/components/ui/empty-state";
import { LabeledSelect } from "@/components/ui/labeled-select";
import { PageIntro } from "@/components/ui/page-intro";
import { filterByRange, type TimeRange } from "@/lib/date-time";
import type { ClinicalAlert } from "@/types";
import { PatientPageError, PatientPageSkeleton } from "./patient-page-state";
import { usePatientOverview } from "./use-patient-overview";

type SeverityFilter = "all" | ClinicalAlert["severity"];
type StatusFilter = "all" | ClinicalAlert["status"];

export function PatientAlertsView() {
  const { state, retry } = usePatientOverview();
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [range, setRange] = useState<TimeRange>("30d");

  if (state.status === "loading") return <PatientPageSkeleton />;
  if (state.status === "error") return <PatientPageError message={state.message} onRetry={retry} />;

  const visibleAlerts = filterByRange(state.data.alerts, range, (alert) => alert.timestamp)
    .filter((alert) => severity === "all" || alert.severity === severity)
    .filter((alert) => status === "all" || alert.status === status)
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <PageIntro title="Alerts" description="Clinical and monitoring alerts associated only with your profile." />

      <div className="grid gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:grid-cols-3">
        <LabeledSelect label="Alert level" value={severity} onChange={(event) => setSeverity(event.target.value as SeverityFilter)}>
          <option value="all">All levels</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Normal</option>
        </LabeledSelect>
        <LabeledSelect label="Status" value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)}>
          <option value="all">All statuses</option>
          <option value="new">New</option>
          <option value="open">Open</option>
          <option value="read">Read</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
        </LabeledSelect>
        <LabeledSelect label="Time range" value={range} onChange={(event) => setRange(event.target.value as TimeRange)}>
          <option value="24h">Last 24 hours</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </LabeledSelect>
      </div>

      {visibleAlerts.length ? (
        <ClinicalAlertTable alerts={visibleAlerts} alertHref={(alert) => `/patient/alerts/${alert.id}`} />
      ) : (
        <EmptyState
          title="No alerts match these filters"
          description="Adjust the alert level, status, or time range to review other alerts."
        />
      )}
    </section>
  );
}
