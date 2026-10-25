"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight } from "lucide-react";
import { PatientMonitoringPanel } from "@/components/clinical/patient-monitoring-panel";
import { LabeledSelect } from "@/components/ui/labeled-select";
import { PageIntro } from "@/components/ui/page-intro";
import { filterByRange, type TimeRange } from "@/lib/date-time";
import { PatientPageError, PatientPageSkeleton } from "./patient-page-state";
import { usePatientOverview } from "./use-patient-overview";

export function PatientMonitoringView() {
  const { state, retry } = usePatientOverview();
  const [range, setRange] = useState<TimeRange>("3h");
  if (state.status === "loading") return <PatientPageSkeleton />;
  if (state.status === "error") return <PatientPageError message={state.message} onRetry={retry} />;

  const { patient, doctor, device, station, events, readings, preferences } = state.data;
  const referenceTimestamps = [
    ...events.map((event) => event.timestamp),
    ...readings.map((reading) => reading.timestamp),
  ];
  const visibleEvents = filterByRange(events, range, (event) => event.timestamp, referenceTimestamps);
  const visibleReadings = filterByRange(readings, range, (reading) => reading.timestamp, referenceTimestamps);

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <PageIntro
        title="My Monitoring"
        actions={
          <>
            <LabeledSelect label="Time range" value={range} onChange={(event) => setRange(event.target.value as TimeRange)}>
              <option value="3h">Last 3 hours</option>
              <option value="6h">Last 6 hours</option>
              <option value="12h">Last 12 hours</option>
              <option value="24h">Last 24 hours</option>
            </LabeledSelect>
            <Link
              href="/patient/history"
              className="inline-flex h-9 items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 text-sm font-medium hover:bg-[var(--color-surface-subtle)]"
            >
              Full history <ArrowRight size={15} aria-hidden />
            </Link>
          </>
        }
      />

      <PatientMonitoringPanel
        patient={patient}
        clinician={doctor}
        device={device}
        station={station}
        events={visibleEvents}
        readings={visibleReadings}
        preferences={preferences}
      />
    </section>
  );
}
