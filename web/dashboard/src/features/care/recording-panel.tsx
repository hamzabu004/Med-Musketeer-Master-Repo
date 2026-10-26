"use client";

import Link from "next/link";
import { useState } from "react";
import { userMessage } from "@/api/errors";
import { useData } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Select } from "@/components/ui/form";
import { Notice } from "@/components/ui/notice";
import { Status, type StatusTone } from "@/components/ui/status";
import { Unavailable } from "@/components/ui/unavailable";
import { isAvailable } from "@/config/capabilities";
import type { RecordingRequest } from "@/services/contracts";
import { formatAgo } from "@/lib/date-time";
import { useAction } from "@/lib/use-action";
import { useResource } from "@/lib/use-resource";
import { usePolling } from "./use-polling";

const noop = () => {};

export function recordingState(r: RecordingRequest): { label: string; tone: StatusTone; open: boolean } {
  if (r.status === "expired") return { label: "No answer from the wearable", tone: "offline", open: false };
  if (r.status === "sent") return { label: "Sent to the wearable", tone: "info", open: true };
  if (r.segment_id === null) return { label: "Recording", tone: "warning", open: true };
  return { label: "Recorded", tone: "healthy", open: false };
}

function Requests({ patientId, hasWearable, segmentHref }: { patientId: string; hasWearable: boolean; segmentHref: (segmentId: string) => string }) {
  const { data } = useData();
  const { busy, notice, run } = useAction();
  const [duration, setDuration] = useState("30");
  const resource = useResource(() => data.recordings.list(patientId), [patientId]);
  const requests = resource.status === "ready" ? resource.data : [];
  // Until the list is read, a recording may be in progress: requesting waits for it.
  const inProgress = resource.status !== "ready" || requests.some((r) => recordingState(r).open);
  // Follows a request through sent, acked and recorded; quiet once nothing is in progress.
  usePolling(requests.some((r) => recordingState(r).open) ? resource.reload : noop, 2_000);

  async function request() {
    if (await run("request", () => data.recordings.request(patientId, Number(duration)), "Request sent to the wearable.")) resource.reload();
  }

  return (
    <Card className="space-y-3 p-4">
      <h3 className="font-semibold">On-demand recording</h3>
      <p className="text-sm text-[var(--color-text-muted)]">
        Asks the patient&apos;s wearable to stream ECG for a set time. The wearable acknowledges the command; the recording then appears as a segment.
      </p>
      {hasWearable ? (
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Length">
            <Select value={duration} onChange={(e) => setDuration(e.target.value)}>
              <option value="10">10 seconds</option>
              <option value="30">30 seconds</option>
              <option value="60">1 minute</option>
            </Select>
          </Field>
          <Button type="button" disabled={busy !== null || inProgress} onClick={() => void request()}>
            {resource.status !== "ready" ? "Request recording" : inProgress ? "Recording in progress" : "Request recording"}
          </Button>
        </div>
      ) : (
        <p className="text-sm text-[var(--color-warning)]">The patient has no wearable issued, so no recording can be requested.</p>
      )}
      <Notice notice={notice} />
      {resource.status === "error" && (
        <p role="alert" className="text-sm text-[var(--color-critical)]">
          Could not read the recording requests: {userMessage(resource.error)}{" "}
          <button type="button" className="underline" onClick={resource.reload}>Try again</button>
        </p>
      )}
      {requests.length > 0 && (
        <ul className="divide-y divide-[var(--color-border)] text-sm">
          {requests.slice(0, 5).map((r) => {
            const state = recordingState(r);
            return (
              <li key={r.command_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>
                  {r.duration_s} s, {formatAgo(r.created_at)} <span className="text-xs text-[var(--color-text-muted)]">({r.path} path)</span>
                </span>
                <span className="flex items-center gap-3">
                  <Status label={state.label} tone={state.tone} />
                  {r.segment_id && <Link href={segmentHref(r.segment_id)} className="text-[var(--color-info)] underline">View ECG</Link>}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export function RecordingPanel(props: { patientId: string; hasWearable: boolean; segmentHref: (segmentId: string) => string }) {
  if (!isAvailable("ecgRequests")) {
    return (
      <Unavailable
        feature="On-demand recording"
        reason="The cloud does not serve recording requests yet: how a recording starts and stops is still being decided. Alert segments below are real."
      />
    );
  }
  return <Requests {...props} />;
}
