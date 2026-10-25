"use client";

import { useState } from "react";
import { Activity, Clock3 } from "lucide-react";
import { ECGWaveform } from "@/components/charts/ecg-waveform";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Status, type StatusTone } from "@/components/ui/status";
import { formatDateTime } from "@/lib/date-time";
import { services } from "@/services";
import type { ECGEvent, ECGRequest, Patient } from "@/types";

const statusLabels: Record<ECGRequest["status"], string> = {
  queued: "Queued",
  "sent-to-device": "Sent to device",
  acquiring: "Recording",
  uploading: "Uploading",
  completed: "Completed",
  failed: "Failed",
  expired: "Timed out",
};

const statusTones: Record<ECGRequest["status"], StatusTone> = {
  queued: "info",
  "sent-to-device": "info",
  acquiring: "warning",
  uploading: "warning",
  completed: "healthy",
  failed: "critical",
  expired: "warning",
};

const activeStatuses: ECGRequest["status"][] = ["queued", "sent-to-device", "acquiring", "uploading"];

export function ECGRequestPanel({
  organizationId,
  patient,
  requestedByUserId,
  requests,
  events,
  onChanged,
}: {
  organizationId: string;
  patient: Patient;
  requestedByUserId: string;
  requests: ECGRequest[];
  events: ECGEvent[];
  onChanged: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const sortedRequests = [...requests].sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
  const activeRequest = sortedRequests.find((request) => activeStatuses.includes(request.status));
  const latestEvent = [...events].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))[0];

  async function requestEcg() {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const request: ECGRequest = await services.ecg.createAcquisitionRequest(organizationId, patient.id, requestedByUserId, "doctor");
      setMessage(`ECG Request - ${statusLabels[request.status]}`);
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "ECG request could not be queued.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold">ECG Acquisition</h3>
        </div>
        <Button type="button" onClick={() => void requestEcg()} disabled={saving || Boolean(activeRequest)}>
          <Activity size={16} aria-hidden /> {saving ? "Queueing..." : "Request ECG"}
        </Button>
      </div>

      {message && <p role="status" className="mt-3 text-sm text-[var(--color-healthy)]">{message}</p>}
      {error && <p role="alert" className="mt-3 text-sm text-[var(--color-critical)]">{error}</p>}

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0">
          <h4 className="text-sm font-semibold">Latest ECG</h4>
          {latestEvent ? (
            <div className="mt-3 space-y-3">
              <ECGWaveform values={latestEvent.waveform} label="Latest ECG recording" />
              <dl className="grid gap-3 text-sm sm:grid-cols-3">
                <Detail label="Acquired" value={formatDateTime(latestEvent.timestamp)} />
                <Detail label="Reason" value={latestEvent.acquisitionReason ?? "Monitoring event"} />
                <Detail label="Result" value={latestEvent.classification[0].toUpperCase() + latestEvent.classification.slice(1)} />
              </dl>
            </div>
          ) : (
            <EmptyState title="No ECG available" description="Completed ECG recordings will appear here." />
          )}
        </div>

        <div>
          <h4 className="text-sm font-semibold">Request Queue</h4>
          {sortedRequests.length ? (
            <div className="mt-3 space-y-3">
              {sortedRequests.slice(0, 4).map((request) => (
                <div key={request.id} className="rounded-[var(--radius-sm)] border border-[var(--color-border)] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium metric-number">{request.id}</span>
                    <Status label={statusLabels[request.status]} tone={statusTones[request.status]} />
                  </div>
                  <p className="mt-2 flex items-center gap-2 text-xs text-[var(--color-text-muted)] metric-number">
                    <Clock3 size={13} aria-hidden /> {formatDateTime(request.createdAt)}
                  </p>
                  <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                    {request.source === "alert" ? "Alert triggered" : "Doctor requested"}
                    {request.failureReason ? ` - ${request.failureReason}` : ""}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No ECG requests" description="Queued ECG requests will appear here." />
          )}
        </div>
      </div>
    </Card>
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
