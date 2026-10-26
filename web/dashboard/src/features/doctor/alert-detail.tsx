"use client";

import Link from "next/link";
import { ApiError } from "@/api/errors";
import type { Alert, PatientSummary, Person, SegmentDetail } from "@/api/types";
import { useData } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Notice } from "@/components/ui/notice";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Status } from "@/components/ui/status";
import { formatAgo, formatDateTime } from "@/lib/date-time";
import { beatLabel, confidence, labelize } from "@/lib/labels";
import { loadPeople } from "@/lib/people";
import { useResource } from "@/lib/use-resource";
import { originLabel, severityTone } from "../care/alert-table";
import { useRenderMarks } from "../care/render-mark";
import { SegmentStrip } from "../care/segment-viewer";
import { useCareNames } from "./care-context";
import { useAcknowledge } from "./use-acknowledge";

export function AlertDetail({ alertId }: { alertId: string }) {
  const { data } = useData();
  const resource = useResource(async () => {
    // The API has no single-alert read: the alert is found among the doctor's newest 1000.
    const [alerts, patients, { people }] = await Promise.all([data.care.alerts({ limit: 1000 }), data.patients(), loadPeople(data.directory)]);
    const alert = alerts.find((a) => a.alert_id === alertId);
    if (!alert) throw new ApiError(404, "alert not found");
    const segment = alert.segment_id ? await data.care.segment(alert.segment_id) : null;
    return { alert, segment, patients, people };
  }, [alertId]);
  const { acknowledge, busy, notice } = useAcknowledge(resource.reload);
  useRenderMarks(resource.status === "ready" ? [resource.data.alert] : null);

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <Loaded resource={resource} label="Loading the alert">
        {({ alert, segment, patients, people }) => (
          <AlertBody alert={alert} segment={segment} patients={patients} people={people} busy={busy} onAcknowledge={() => void acknowledge(alert)} notice={<Notice notice={notice} />} />
        )}
      </Loaded>
    </section>
  );
}

function AlertBody({ alert, segment, patients, people, busy, onAcknowledge, notice }: {
  alert: Alert;
  segment: SegmentDetail | null;
  patients: PatientSummary[];
  people: Person[];
  busy: boolean;
  onAcknowledge: () => void;
  notice: React.ReactNode;
}) {
  const names = useCareNames(patients, people);
  const patient = names.patient(alert);
  return (
    <>
      <PageIntro
        title={beatLabel(alert.label)}
        description={`${patient.label} · ${formatDateTime(alert.created_at)} (${formatAgo(alert.created_at)})`}
        actions={
          alert.acknowledged_at ? (
            <Status label={`Acknowledged by ${names.person(alert.acknowledged_by!)}`} tone="healthy" />
          ) : (
            <Button type="button" disabled={busy} onClick={onAcknowledge}>Acknowledge</Button>
          )
        }
      />
      <p className="text-sm">
        <Link href="/doctor/alerts" className="text-[var(--color-info)] underline">All alerts</Link>
        <Link href={patient.href} className="ml-4 text-[var(--color-info)] underline">{patient.label}&apos;s page</Link>
      </p>
      {notice}
      <Card className="p-4">
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          {([
            ["Severity", <Status key="s" label={labelize(alert.severity)} tone={severityTone(alert.severity)} />],
            ["Confidence", confidence(alert.confidence)],
            ["Classified by", originLabel(alert.origin)],
            ["Wearable", <RecordId key="w" id={alert.device_id} />],
            ["Acknowledged", alert.acknowledged_at ? formatDateTime(alert.acknowledged_at) : "Not yet"],
          ] as const).map(([term, value]) => (
            <div key={term}>
              <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">{term}</dt>
              <dd className="mt-0.5">{value}</dd>
            </div>
          ))}
        </dl>
      </Card>
      {segment ? <SegmentStrip segment={segment} /> : <p className="text-sm text-[var(--color-text-muted)]">This alert has no ECG segment attached.</p>}
    </>
  );
}
