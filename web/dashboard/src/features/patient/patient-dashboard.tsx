"use client";

import Link from "next/link";
import { Activity, ArrowRight, History } from "lucide-react";
import { ClinicalAlertTable } from "@/components/clinical/clinical-alert-table";
import { ECGEventList } from "@/components/clinical/ecg-event-list";
import { MonitoringSummary } from "@/components/clinical/monitoring-summary";
import { ConnectionNotice } from "@/components/monitoring/connection-notice";
import { DeviceStatusCard } from "@/components/monitoring/device-status-card";
import { MonitoringStationCard } from "@/components/monitoring/monitoring-station-card";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageIntro } from "@/components/ui/page-intro";
import { formatDateTime } from "@/lib/date-time";
import { PatientPageError, PatientPageSkeleton } from "./patient-page-state";
import { usePatientOverview } from "./use-patient-overview";

const actionClass =
  "inline-flex h-9 items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 text-sm font-medium hover:bg-[var(--color-surface-subtle)]";

export function PatientDashboard() {
  const { state, retry } = usePatientOverview();
  if (state.status === "loading") return <PatientPageSkeleton />;
  if (state.status === "error") return <PatientPageError message={state.message} onRetry={retry} />;

  const { patient, device, station, alerts, events, readings, preferences } = state.data;
  const latestReading = [...readings].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))[0];
  const recentAlerts = [...alerts]
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
    .slice(0, 3);
  const recentEvents = [...events]
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
    .slice(0, 3);

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <PageIntro
        title={`Hello, ${patient.displayName}`}
        description={`Latest simulated update: ${formatDateTime(patient.lastUpdatedAt)}`}
        actions={
          <>
            <Link href="/patient/monitoring" className={actionClass}>
              <Activity size={16} aria-hidden /> My Monitoring
            </Link>
            <Link href="/patient/history" className={actionClass}>
              <History size={16} aria-hidden /> My History
            </Link>
          </>
        }
      />

      <ConnectionNotice device={device} station={station} classification={patient.ecgClassification} />

      <MonitoringSummary
        heartRate={latestReading?.bpm ?? patient.currentHeartRate}
        classification={patient.ecgClassification}
        latestHeartRateAt={latestReading?.timestamp ?? patient.lastUpdatedAt}
        heartRateIntervalSeconds={preferences.heartRateMonitoringIntervalSeconds}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        {device ? (
          <DeviceStatusCard device={device} />
        ) : (
          <EmptyState title="No wearable assigned" description="A wearable has not been assigned to this profile." />
        )}
        {station ? (
          <MonitoringStationCard station={station} />
        ) : (
          <EmptyState title="No Monitoring Station assigned" description="Monitoring Station information is not available for this profile." />
        )}
      </div>

      <div className="grid gap-5">
        <section aria-labelledby="recent-alerts-heading" className="min-w-0 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 id="recent-alerts-heading" className="text-lg font-semibold">Recent alerts</h3>
            <Link href="/patient/alerts" className="inline-flex items-center gap-1 text-sm font-medium text-[var(--color-info)] hover:underline">
              View all <ArrowRight size={14} aria-hidden />
            </Link>
          </div>
          {recentAlerts.length ? (
            <ClinicalAlertTable alerts={recentAlerts} alertHref={(alert) => `/patient/alerts/${alert.id}`} />
          ) : (
            <EmptyState title="No recent alerts" description="There are no alerts for your monitoring profile." />
          )}
        </section>

        <section aria-labelledby="recent-history-heading" className="min-w-0 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 id="recent-history-heading" className="text-lg font-semibold">Recent history</h3>
            <Link href="/patient/history" className="inline-flex items-center gap-1 text-sm font-medium text-[var(--color-info)] hover:underline">
              Full history <ArrowRight size={14} aria-hidden />
            </Link>
          </div>
          {recentEvents.length ? (
            <ECGEventList events={recentEvents} />
          ) : (
            <EmptyState title="No recent history" description="Monitoring events will appear here when available." />
          )}
        </section>
      </div>

      <Card className="p-4 text-sm text-[var(--color-text-muted)]">
        Values shown here are simulated and are not medical advice.
      </Card>
    </section>
  );
}
