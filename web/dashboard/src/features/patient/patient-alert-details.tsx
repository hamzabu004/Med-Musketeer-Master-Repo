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
import { PatientPageError, PatientPageSkeleton } from "./patient-page-state";
import { usePatientOverview } from "./use-patient-overview";

const severityTone: Record<ClinicalAlert["severity"], StatusTone> = {
  info: "healthy",
  warning: "warning",
  critical: "critical",
};

const severityLabels: Record<ClinicalAlert["severity"], string> = {
  info: "Normal",
  warning: "Warning",
  critical: "Critical",
};

const explanations: Record<ClinicalAlert["type"], string> = {
  ecg: "The simulated monitoring system recorded an ECG event outside its normal classification.",
  device: "Your wearable reported a connection or device-status change. This does not indicate a physiological change.",
  "monitoring-station": "The Monitoring Station reported a connection-status change. This does not indicate a physiological change.",
  monitoring: "Your simulated monitoring record was updated.",
};

export function PatientAlertDetails({ alertId }: { alertId: string }) {
  const { state, retry } = usePatientOverview();
  const [updating, setUpdating] = useState(false);
  const [updateError, setUpdateError] = useState("");

  if (state.status === "loading") return <PatientPageSkeleton />;
  if (state.status === "error") return <PatientPageError message={state.message} onRetry={retry} />;

  const alert = state.data.alerts.find((item) => item.id === alertId);
  if (!alert) {
    return (
      <section className="mx-auto max-w-4xl space-y-5">
        <Link href="/patient/alerts" className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-info)] hover:underline">
          <ArrowLeft size={15} aria-hidden /> Back to alerts
        </Link>
        <EmptyState title="Alert not found" description="This alert is not available for your Patient profile." />
      </section>
    );
  }

  const data = state.data;
  const organizationId = data.session.organizationId;
  const event = alert.eventId ? data.events.find((item) => item.id === alert.eventId) : undefined;
  const classification = alert.ecgClassification ?? event?.classification;
  const heartRate = alert.heartRate ?? event?.heartRate;
  const currentAlertId = alert.id;

  async function markRead() {
    setUpdating(true);
    setUpdateError("");
    try {
      await services.clinicalAlerts.markRead(organizationId, currentAlertId);
      retry();
    } catch {
      setUpdateError("The alert could not be updated. Please try again.");
      setUpdating(false);
    }
  }

  return (
    <section className="mx-auto max-w-4xl space-y-5">
      <Link href="/patient/alerts" className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-info)] hover:underline">
        <ArrowLeft size={15} aria-hidden /> Back to alerts
      </Link>
      <PageIntro
        title="Alert Details"
        description="Patient-appropriate information from your simulated monitoring record."
        actions={
          alert.status !== "read" && alert.status !== "resolved" ? (
            <Button type="button" variant="secondary" disabled={updating} onClick={markRead}>
              {updating ? "Updating…" : "Mark as read"}
            </Button>
          ) : undefined
        }
      />

      {updateError && <p role="alert" className="text-sm text-[var(--color-critical)]">{updateError}</p>}

      <Card className="p-5">
        <div className="flex flex-col gap-3 border-b border-[var(--color-border)] pb-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Event</p>
            <h3 className="mt-1 text-lg font-semibold">{alert.title}</h3>
          </div>
          <Status label={severityLabels[alert.severity]} tone={severityTone[alert.severity]} />
        </div>
        <dl className="mt-4 grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
          <Detail label="Recorded at" value={formatDateTime(alert.timestamp)} />
          <Detail label="Status" value={alert.status[0].toUpperCase() + alert.status.slice(1)} />
          <Detail label="ECG result" value={classification ? classification[0].toUpperCase() + classification.slice(1) : "Normal"} />
          <Detail label="Heart rate" value={heartRate == null ? "Not available" : `${heartRate} bpm`} />
        </dl>
      </Card>

      <Card className="p-5">
        <h3 className="font-semibold">What this means</h3>
        <p className="mt-2 text-sm leading-6 text-[var(--color-text-muted)]">{explanations[alert.type]}</p>
        <p className="mt-2 text-sm leading-6 text-[var(--color-text-muted)]">
          This simulated record does not provide a diagnosis or treatment recommendation.
        </p>
      </Card>

      {event && (
        <section aria-labelledby="event-segment-heading" className="space-y-3">
          <div>
            <h3 id="event-segment-heading" className="text-lg font-semibold">Recorded ECG segment</h3>
          </div>
          <ECGWaveform values={event.waveform} label="Simulated recorded ECG event segment" />
        </section>
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
