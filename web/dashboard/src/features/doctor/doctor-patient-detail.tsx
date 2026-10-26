"use client";

import Link from "next/link";
import type { Alert, OrgDevice, PatientSummary, Person, Segment } from "@/api/types";
import { ApiError } from "@/api/errors";
import { useData } from "@/auth/session";
import { Card } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/metric";
import { Notice } from "@/components/ui/notice";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { loadPeople, NAMES_UNAVAILABLE } from "@/lib/people";
import { useResource } from "@/lib/use-resource";
import { AlertTable } from "../care/alert-table";
import { RecordingPanel } from "../care/recording-panel";
import { SegmentTable } from "../care/segment-table";
import { ALERT_POLL_MS, usePolling } from "../care/use-polling";
import { WearableStatus } from "../care/wearable-status";
import { useCareNames } from "./care-context";
import { useAcknowledge } from "./use-acknowledge";

export function DoctorPatientDetail({ patientId }: { patientId: string }) {
  const { data } = useData();
  const resource = useResource(async () => {
    const [patients, disorders, devices, alerts, segments, { people, named }] = await Promise.all([
      data.patients(), data.disorders(patientId), data.devices(), data.care.patientAlerts(patientId, { limit: 200 }),
      data.care.segments(patientId), loadPeople(data.directory),
    ]);
    const patient = patients.find((p) => p.patient_id === patientId);
    if (!patient) throw new ApiError(404, "patient not found");
    return { patient, patients, disorders, devices, alerts, segments, people, named };
  }, [patientId]);
  usePolling(resource.reload, ALERT_POLL_MS);
  const { acknowledge, busy, notice } = useAcknowledge(resource.reload);

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <Loaded resource={resource} label="Loading the patient">
        {(loaded) => <Body {...loaded} onAcknowledge={acknowledge} busy={busy} notice={<Notice notice={notice} />} />}
      </Loaded>
    </section>
  );
}

function Body({ patient, patients, disorders, devices, alerts, segments, people, named, onAcknowledge, busy, notice }: {
  patient: PatientSummary; patients: PatientSummary[]; disorders: { disorder: string }[]; devices: OrgDevice[];
  alerts: Alert[]; segments: Segment[]; people: Person[]; named: boolean;
  onAcknowledge: (alert: Alert) => void; busy: boolean; notice: React.ReactNode;
}) {
  const names = useCareNames(patients, people);
  const wearable = devices.find((d) => d.device_id === patient.wearable_id) ?? null;
  const open = alerts.filter((a) => !a.acknowledged_at).length;
  return (
    <>
      <PageIntro title={patient.pseudonym} description={`${names.patientName(patient) ?? "Name not available"} · ${open} unacknowledged ${open === 1 ? "alert" : "alerts"}`} />
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
        busy={busy}
        empty={{ title: "No alerts", description: "Alerts raised by this patient's wearable appear here." }}
      />
      <SectionTitle>ECG segments</SectionTitle>
      <SegmentTable segments={segments} href={(s) => `/doctor/patients/${patient.patient_id}/segments/${s.segment_id}`} />
    </>
  );
}
