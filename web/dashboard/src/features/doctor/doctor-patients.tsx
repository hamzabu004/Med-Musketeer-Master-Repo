"use client";

import { useState } from "react";
import { PatientTable } from "@/components/clinical/patient-table";
import { EmptyState } from "@/components/ui/empty-state";
import { LabeledSelect } from "@/components/ui/labeled-select";
import { PageIntro } from "@/components/ui/page-intro";
import type { Patient } from "@/types";
import { DoctorPageError, DoctorPageSkeleton } from "./doctor-page-state";
import { useDoctorOverview } from "./use-doctor-overview";

type StatusFilter = "all" | Patient["monitoringState"];
const priorityRank = { attention: 0, offline: 1, unknown: 2, normal: 3 } as const;

export function DoctorPatients() {
  const { state, retry } = useDoctorOverview();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");

  if (state.status === "loading") return <DoctorPageSkeleton />;
  if (state.status === "error") return <DoctorPageError message={state.message} onRetry={retry} />;

  const normalizedQuery = query.trim().toLowerCase();
  const visiblePatients = state.data.patients
    .filter((patient) => !normalizedQuery || patient.displayName.toLowerCase().includes(normalizedQuery))
    .filter((patient) => status === "all" || patient.monitoringState === status)
    .sort((a, b) => priorityRank[a.monitoringState] - priorityRank[b.monitoringState]);

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Patients" description="Only patients assigned to your clinician profile are shown." />

      <div className="grid gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:grid-cols-[minmax(0,1fr)_14rem]">
        <label className="block text-sm font-medium">
          Search patients
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by patient name"
            className="mt-1 h-9 w-full rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 text-sm"
          />
        </label>
        <LabeledSelect label="Monitoring status" value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)}>
          <option value="all">All statuses</option>
          <option value="attention">Attention required</option>
          <option value="offline">Monitoring offline</option>
          <option value="normal">Monitoring active</option>
          <option value="unknown">Status unknown</option>
        </LabeledSelect>
      </div>

      <p className="text-sm text-[var(--color-text-muted)]" role="status">
        Showing {visiblePatients.length} of {state.data.patients.length} registered patients
      </p>

      {visiblePatients.length ? (
        <PatientTable
          patients={visiblePatients}
          stations={state.data.stations}
          readings={state.data.readings}
          heartRateIntervalSeconds={state.data.preferences.heartRateMonitoringIntervalSeconds}
        />
      ) : (
        <EmptyState title="No matching patients" description="Adjust the search or monitoring-status filter." />
      )}
    </section>
  );
}
