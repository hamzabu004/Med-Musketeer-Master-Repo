"use client";

import Link from "next/link";
import type { Alert, Disorder, OrgDevice, PatientSummary, Person, Segment } from "@/api/types";
import { ApiError, userMessage } from "@/api/errors";
import { useData } from "@/auth/session";
import { Card } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { SectionTitle } from "@/components/ui/metric";
import { Notice } from "@/components/ui/notice";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { NAMES_UNAVAILABLE } from "@/lib/people";
import { useResource } from "@/lib/use-resource";
import { AlertTable } from "../care/alert-table";
import { ALERT_LIMIT, countLabel } from "../care/limits";
import { RecordingPanel } from "../care/recording-panel";
import { SegmentTable } from "../care/segment-table";
import { ALERT_POLL_MS, usePolling } from "../care/use-polling";
import { WearableStatus } from "../care/wearable-status";
import { useCareContext, useCareNames } from "./care-context";
import { useAcknowledge } from "./use-acknowledge";

/** How many of the patient's alerts and segments the page lists. */
const LISTED = 200;

export function DoctorPatientDetail({ patientId }: { patientId: string }) {
  const { data } = useData();
  const context = useCareContext();
  const disorders = useResource(() => data.disorders(patientId), [patientId]);
  // Polled: alerts (the newest listed, and every unacknowledged one for the count) and segments.
  const care = useResource(async () => {
    const [alerts, open, segments] = await Promise.all([
      data.care.patientAlerts(patientId, { limit: LISTED }),
      data.care.patientAlerts(patientId, { unacknowledged: true, limit: ALERT_LIMIT }),
      data.care.segments(patientId, LISTED),
    ]);
    return { alerts, open: open.length, segments };
  }, [patientId]);
  usePolling(care.reload, ALERT_POLL_MS);
  const { acknowledge, isPending, notice } = useAcknowledge(care.reload);

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <Loaded resource={context} label="Loading the patient">
        {({ patients, devices, people, named }) => {
          const patient = patients.find((p) => p.patient_id === patientId);
          // Not one of this doctor's current patients: answered as the API answers (D9 404).
          if (!patient) return <ErrorState title="Could not load this page" description={userMessage(new ApiError(404, "patient not found"))} onRetry={context.reload} />;
          return (
            <Loaded resource={disorders} label="Loading the patient">
              {(list) => (
                <Loaded resource={care} label="Loading alerts">
                  {(c) => (
                    <Body patient={patient} patients={patients} devices={devices} people={people} named={named} disorders={list} {...c} onAcknowledge={acknowledge} isPending={isPending} notice={<Notice notice={notice} />} />
                  )}
                </Loaded>
              )}
            </Loaded>
          );
        }}
      </Loaded>
    </section>
  );
}

function Body({ patient, patients, disorders, devices, alerts, open, segments, people, named, onAcknowledge, isPending, notice }: {
  patient: PatientSummary; patients: PatientSummary[]; disorders: Disorder[]; devices: OrgDevice[];
  alerts: Alert[]; open: number; segments: Segment[]; people: Person[]; named: boolean;
  onAcknowledge: (alert: Alert) => void; isPending: (alert: Alert) => boolean; notice: React.ReactNode;
}) {
  const names = useCareNames(patients, people);
  const wearable = devices.find((d) => d.device_id === patient.wearable_id) ?? null;
  return (
    <>
      <PageIntro title={patient.pseudonym} description={`${names.patientName(patient) ?? "Name not available"} · ${countLabel(open)} unacknowledged ${open === 1 ? "alert" : "alerts"}`} />
      <p className="text-sm"><Link href="/doctor/patients" className="text-[var(--color-info)] underline">All patients</Link></p>
      {!named && <p className="text-xs text-[var(--color-text-muted)]">{NAMES_UNAVAILABLE}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <WearableStatus wearable={wearable} />
        <Card className="space-y-2 p-4">
          <h3 className="font-semibold">Known disorders</h3>
          {disorders.length ? (
            <ul className="list-disc pl-5 text-sm">{disorders.map((d) => <li key={d.disorder}>{d.disorder}</li>)}</ul>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">None recorded.</p>
          )}
        </Card>
      </div>
      <RecordingPanel patientId={patient.patient_id} hasWearable={wearable !== null} segmentHref={(id) => `/doctor/patients/${patient.patient_id}/segments/${id}`} />
      <SectionTitle>Alerts</SectionTitle>
      {notice}
      <AlertTable
        alerts={alerts}
        detailHref={(a) => `/doctor/alerts/${a.alert_id}`}
        acknowledgedBy={names.person}
        onAcknowledge={onAcknowledge}
        isPending={isPending}
        empty={{ title: "No alerts", description: "Alerts raised by this patient's wearable appear here." }}
      />
      {alerts.length >= LISTED && <p className="text-xs text-[var(--color-text-muted)]">Showing the newest {LISTED} alerts.</p>}
      <SectionTitle>ECG segments</SectionTitle>
      <SegmentTable segments={segments} href={(s) => `/doctor/patients/${patient.patient_id}/segments/${s.segment_id}`} />
      {segments.length >= LISTED && <p className="text-xs text-[var(--color-text-muted)]">Showing the newest {LISTED} segments.</p>}
    </>
  );
}
