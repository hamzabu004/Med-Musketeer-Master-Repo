"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { ECGWaveform } from "@/components/charts/ecg-waveform";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageIntro } from "@/components/ui/page-intro";
import { Status, type StatusTone } from "@/components/ui/status";
import { formatDateTime } from "@/lib/date-time";
import { services } from "@/services";
import type { ClinicalAlert } from "@/types";
import { DoctorPageError, DoctorPageSkeleton } from "./doctor-page-state";
import { useDoctorOverview } from "./use-doctor-overview";

const severityTones: Record<ClinicalAlert["severity"], StatusTone> = {
  info: "healthy",
  warning: "warning",
  critical: "critical",
};

const severityLabels: Record<ClinicalAlert["severity"], string> = {
  info: "Normal",
  warning: "Warning",
  critical: "Critical",
};

export function DoctorAlertDetails({ alertId }: { alertId: string }) {
  const { state, retry } = useDoctorOverview();
  const [acknowledging, setAcknowledging] = useState(false);
  const [actionError, setActionError] = useState("");

  if (state.status === "loading") return <DoctorPageSkeleton />;
  if (state.status === "error") return <DoctorPageError message={state.message} onRetry={retry} />;

  const alert = state.data.alerts.find((item) => item.id === alertId);
  if (!alert) {
    return (
      <section className="mx-auto max-w-5xl space-y-5">
        <Link href="/doctor/alerts" className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-info)] hover:underline">
          <ArrowLeft size={15} aria-hidden /> Back to alerts
        </Link>
        <EmptyState title="Clinical event not found" description="This event does not belong to a registered patient or is unavailable." />
      </section>
    );
  }

  const data = state.data;
  const organizationId = data.session.organizationId;
  const patient = data.patients.find((item) => item.id === alert.patientId);
  const event = alert.eventId ? data.events.find((item) => item.id === alert.eventId) : undefined;
  const deviceId = event?.deviceId ?? patient?.deviceId;
  const stationId = event?.monitoringStationId ?? patient?.monitoringStationId;
  const device = data.devices.find((item) => item.id === deviceId);
  const station = data.stations.find((item) => item.id === stationId);
  const classification = event?.classification ?? alert.ecgClassification;
  const heartRate = event?.heartRate ?? alert.heartRate;
  const currentAlertId = alert.id;

  async function acknowledge() {
    setAcknowledging(true);
    setActionError("");
    try {
      await services.clinicalAlerts.acknowledge(organizationId, currentAlertId);
      retry();
    } catch {
      setActionError("The alert could not be acknowledged. Please try again.");
      setAcknowledging(false);
    }
  }

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <Link href="/doctor/alerts" className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-info)] hover:underline">
        <ArrowLeft size={15} aria-hidden /> Back to alerts
      </Link>
      <PageIntro
        title="Clinical Event Details"
        description="Fixed event data from the simulated monitoring record."
        actions={
          alert.status !== "acknowledged" && alert.status !== "resolved" ? (
            <Button type="button" disabled={acknowledging} onClick={acknowledge}>
              {acknowledging ? "Acknowledging…" : "Acknowledge alert"}
            </Button>
          ) : undefined
        }
      />
      {actionError && <p role="alert" className="text-sm text-[var(--color-critical)]">{actionError}</p>}

      <Card className="p-5">
        <div className="flex flex-col gap-3 border-b border-[var(--color-border)] pb-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">{event?.id ?? alert.id}</p>
            <h3 className="mt-1 text-lg font-semibold">{alert.title}</h3>
          </div>
          <Status label={severityLabels[alert.severity]} tone={severityTones[alert.severity]} />
        </div>

        <dl className="mt-4 grid gap-x-8 gap-y-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <dt className="text-[var(--color-text-muted)]">Patient</dt>
            <dd className="mt-1 font-medium metric-number">
              {patient ? (
                <Link href={`/doctor/patients/${patient.id}`} className="text-[var(--color-info)] underline-offset-2 hover:underline">
                  {patient.displayName}
                </Link>
              ) : "Unavailable"}
            </dd>
          </div>
          <Detail label="Alert ID" value={alert.id} />
          <Detail label="ECG event ID" value={event?.id ?? "None"} />
          <Detail label="Recorded at" value={formatDateTime(alert.timestamp)} />
          <Detail label="ECG classification" value={classification ? classification[0].toUpperCase() + classification.slice(1) : "Normal"} />
          <Detail label="Heart rate" value={heartRate == null ? "Not available" : `${heartRate} bpm`} />
          {event?.confidence != null && <Detail label="Model confidence" value={`${Math.round(event.confidence * 100)}%`} />}
          <Detail label="Wearable" value={device?.id ?? "Not assigned"} />
          <Detail label="Monitoring Station" value={station ? `${station.name} (${station.id})` : "Not assigned"} />
          <Detail label="Event duration" value={event?.durationSeconds == null ? "Not available" : `${event.durationSeconds} seconds`} />
          <Detail label="Alert status" value={alert.status[0].toUpperCase() + alert.status.slice(1)} />
        </dl>
      </Card>

      {event ? (
        <section aria-labelledby="fixed-event-strip-heading" className="space-y-3">
          <div>
            <h3 id="fixed-event-strip-heading" className="text-lg font-semibold">Fixed ECG event strip</h3>
          </div>
          <ECGWaveform values={event.waveform} label={`Simulated ECG event ${event.id}`} />
        </section>
      ) : (
        <EmptyState title="No ECG strip for this alert" description="This monitoring alert is not associated with a recorded ECG segment." />
      )}
    </section>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[var(--color-text-muted)]">{label}</dt>
      <dd className="mt-1 font-medium metric-number">{value}</dd>
    </div>
  );
}
