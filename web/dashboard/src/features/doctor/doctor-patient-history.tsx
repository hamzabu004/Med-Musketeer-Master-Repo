"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { ClassificationDistributionChart, EventFrequencyChart } from "@/components/charts/clinical-event-charts";
import { HeartRateTrend } from "@/components/charts/heart-rate-trend";
import { ECGEventList } from "@/components/clinical/ecg-event-list";
import { EventTimeline } from "@/components/clinical/event-timeline";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { LabeledSelect } from "@/components/ui/labeled-select";
import { PageIntro } from "@/components/ui/page-intro";
import { filterByRange, formatChartTime, type TimeRange } from "@/lib/date-time";
import { DoctorPageError, DoctorPageSkeleton } from "./doctor-page-state";
import { useDoctorOverview } from "./use-doctor-overview";

export function DoctorPatientHistory({ patientId }: { patientId: string }) {
  const { state, retry } = useDoctorOverview();
  const [range, setRange] = useState<TimeRange>("7d");

  if (state.status === "loading") return <DoctorPageSkeleton />;
  if (state.status === "error") return <DoctorPageError message={state.message} onRetry={retry} />;

  const patient = state.data.patients.find((item) => item.id === patientId);
  if (!patient) {
    return (
      <section className="mx-auto max-w-6xl space-y-5">
        <Link href="/doctor/patients" className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-info)] hover:underline">
          <ArrowLeft size={15} aria-hidden /> Back to patients
        </Link>
        <EmptyState title="Patient history unavailable" description="This patient is not assigned to your clinician profile." />
      </section>
    );
  }

  const patientEvents = state.data.events.filter((event) => event.patientId === patient.id);
  const patientReadings = state.data.readings.filter((reading) => reading.patientId === patient.id);
  const patientAlerts = state.data.alerts.filter((alert) => alert.patientId === patient.id);
  const referenceTimestamps = [
    ...patientEvents.map((event) => event.timestamp),
    ...patientReadings.map((reading) => reading.timestamp),
    ...patientAlerts.map((alert) => alert.timestamp),
  ];
  const events = filterByRange(patientEvents, range, (event) => event.timestamp, referenceTimestamps)
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  const readings = filterByRange(patientReadings, range, (reading) => reading.timestamp, referenceTimestamps);
  const alerts = filterByRange(patientAlerts, range, (alert) => alert.timestamp, referenceTimestamps);
  const chartData = [...readings]
    .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
    .map((reading) => ({ time: formatChartTime(reading.timestamp), bpm: reading.bpm }));

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <Link href={`/doctor/patients/${patient.id}`} className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-info)] hover:underline">
        <ArrowLeft size={15} aria-hidden /> Back to patient profile
      </Link>
      <PageIntro
        title={`${patient.displayName} — History`}
        description="Clinical review of simulated readings, ECG events, and alert activity."
        actions={
          <LabeledSelect label="Time range" value={range} onChange={(event) => setRange(event.target.value as TimeRange)}>
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </LabeledSelect>
        }
      />

      <Card className="grid gap-px overflow-hidden bg-[var(--color-border)] sm:grid-cols-3">
        <Summary label="ECG events" value={events.length} />
        <Summary label="Abnormal events" value={events.filter((event) => event.classification === "abnormal").length} />
        <Summary label="Clinical alerts" value={alerts.length} />
      </Card>

      <Card className="p-4">
        <h3 className="text-lg font-semibold">Heart-rate trend</h3>
        {chartData.length ? <HeartRateTrend data={chartData} /> : <EmptyState title="No heart-rate readings" description="No readings are available for this patient in the selected range." />}
      </Card>

      {events.length ? (
        <div className="grid gap-4 xl:grid-cols-2">
          <Card className="min-w-0 p-4">
            <h3 className="text-lg font-semibold">Event frequency</h3>
            <EventFrequencyChart events={events} />
          </Card>
          <Card className="min-w-0 p-4">
            <h3 className="text-lg font-semibold">Classification distribution</h3>
            <ClassificationDistributionChart events={events} />
          </Card>
        </div>
      ) : (
        <EmptyState title="No ECG analytics" description="No ECG events are available for this patient in the selected range." />
      )}

      <section aria-labelledby="doctor-event-timeline-heading" className="space-y-3">
        <h3 id="doctor-event-timeline-heading" className="text-lg font-semibold">Event timeline</h3>
        <EventTimeline events={events} />
      </section>

      <section aria-labelledby="doctor-ecg-events-heading" className="min-w-0 space-y-3">
        <h3 id="doctor-ecg-events-heading" className="text-lg font-semibold">ECG events</h3>
        {events.length ? <ECGEventList events={events} /> : <EmptyState title="No ECG events" description="No events are available for this patient in the selected range." />}
      </section>
    </section>
  );
}

function Summary({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-[var(--color-surface)] p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">{label}</p>
      <p className="mt-2 text-2xl font-semibold metric-number">{value}</p>
    </div>
  );
}
