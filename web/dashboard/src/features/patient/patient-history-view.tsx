"use client";

import { useState } from "react";
import { HeartRateTrend } from "@/components/charts/heart-rate-trend";
import { ECGEventList } from "@/components/clinical/ecg-event-list";
import { EventTimeline } from "@/components/clinical/event-timeline";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { LabeledSelect } from "@/components/ui/labeled-select";
import { PageIntro } from "@/components/ui/page-intro";
import { filterByRange, formatChartTime, type TimeRange } from "@/lib/date-time";
import { PatientPageError, PatientPageSkeleton } from "./patient-page-state";
import { usePatientOverview } from "./use-patient-overview";

export function PatientHistoryView() {
  const { state, retry } = usePatientOverview();
  const [range, setRange] = useState<TimeRange>("24h");

  if (state.status === "loading") return <PatientPageSkeleton />;
  if (state.status === "error") return <PatientPageError message={state.message} onRetry={retry} />;

  const { readings, events, alerts } = state.data;
  const referenceTimestamps = [
    ...readings.map((reading) => reading.timestamp),
    ...events.map((event) => event.timestamp),
    ...alerts.map((alert) => alert.timestamp),
  ];
  const visibleReadings = filterByRange(readings, range, (reading) => reading.timestamp, referenceTimestamps);
  const visibleEvents = filterByRange(events, range, (event) => event.timestamp, referenceTimestamps)
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  const visibleAlerts = filterByRange(alerts, range, (alert) => alert.timestamp, referenceTimestamps);
  const abnormalCount = visibleEvents.filter((event) => event.classification === "abnormal").length;
  const chartData = [...visibleReadings]
    .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp))
    .map((reading) => ({ time: formatChartTime(reading.timestamp), bpm: reading.bpm }));

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <PageIntro
        title="My History"
        description="Review simulated heart-rate readings and recorded ECG events."
        actions={
          <LabeledSelect label="Time range" value={range} onChange={(event) => setRange(event.target.value as TimeRange)}>
            <option value="3h">Last 3 hours</option>
            <option value="6h">Last 6 hours</option>
            <option value="12h">Last 12 hours</option>
            <option value="24h">Last 24 hours</option>
          </LabeledSelect>
        }
      />

      <div className="grid gap-3 sm:grid-cols-3">
        <SummaryValue label="ECG events" value={visibleEvents.length} />
        <SummaryValue label="Abnormal events" value={abnormalCount} tone={abnormalCount ? "critical" : undefined} />
        <SummaryValue label="Alerts" value={visibleAlerts.length} />
      </div>

      <Card className="p-4">
        <div className="mb-3">
          <h3 className="text-lg font-semibold">Heart-rate trend</h3>
        </div>
        {chartData.length ? (
          <HeartRateTrend data={chartData} />
        ) : (
          <EmptyState title="No heart-rate readings" description="No readings are available in the selected time range." />
        )}
      </Card>

      <section aria-labelledby="event-timeline-heading" className="space-y-3">
        <h3 id="event-timeline-heading" className="text-lg font-semibold">Event timeline</h3>
        <EventTimeline events={visibleEvents} />
      </section>

      <section aria-labelledby="ecg-history-heading" className="space-y-3">
        <h3 id="ecg-history-heading" className="text-lg font-semibold">ECG event history</h3>
        {visibleEvents.length ? (
          <ECGEventList events={visibleEvents} />
        ) : (
          <EmptyState title="No ECG events" description="No ECG events are available in the selected time range." />
        )}
      </section>
    </section>
  );
}

function SummaryValue({ label, value, tone }: { label: string; value: number; tone?: "critical" }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">{label}</p>
      <p className={`mt-2 text-2xl font-semibold metric-number ${tone ? "text-[var(--color-critical)]" : ""}`}>{value}</p>
    </Card>
  );
}
