"use client";

import Link from "next/link";
import { ApiError } from "@/api/errors";
import type { Person } from "@/api/types";
import { useData } from "@/auth/session";
import { Card } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/metric";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { labelize } from "@/lib/labels";
import { loadPeople, personName } from "@/lib/people";
import { useResource } from "@/lib/use-resource";
import { AlertTable } from "../care/alert-table";
import { ALERT_LIMIT } from "../care/limits";
import { ALERT_POLL_MS, usePolling } from "../care/use-polling";
import { SegmentTable } from "../care/segment-table";

function MedicalNotice() {
  return (
    <p className="border-l-2 border-[var(--color-warning)] px-3 py-2 text-sm">
      MedMusketeer is a research prototype, not a medical device, and its classifications are not medical advice. If you feel unwell, contact your doctor or emergency services; do not wait for an alert.
    </p>
  );
}

/** Who acknowledged: the patient sees their own doctor by name (the directory gives them only that doctor). */
function acknowledger(people: Person[]) {
  return (userId: string) => personName(people.find((p) => p.user_id === userId)) ?? "Your doctor";
}

const segmentHref = (segmentId: string | null) => (segmentId ? `/patient/ecg/${segmentId}` : null);

export function PatientDashboard() {
  const { data } = useData();
  const resource = useResource(async () => {
    const [organisation, { people }] = await Promise.all([data.organisation(), loadPeople(data.directory)]);
    return { organisation, people };
  }, []);
  // Only the alerts are polled; the organisation and names are read once.
  const latest = useResource(() => data.care.alerts({ limit: 5 }), []);
  usePolling(latest.reload, ALERT_POLL_MS);

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <PageIntro title="Dashboard" description="Your monitoring at a glance. Your doctor reviews every alert; this page is for your information." />
      <MedicalNotice />
      <Loaded resource={resource} label="Loading your monitoring">
        {({ organisation, people }) => {
          const doctor = people.find((p) => p.role === "doctor");
          return (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <Card className="p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">Your organisation</p>
                  <p className="mt-1 font-semibold">{organisation.name}</p>
                  <p className="text-sm text-[var(--color-text-muted)]">{labelize(organisation.kind)} organisation</p>
                </Card>
                <Card className="p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">Your doctor</p>
                  <p className="mt-1 font-semibold">{doctor ? (personName(doctor) ?? "Assigned") : "Not assigned yet"}</p>
                  <p className="text-sm text-[var(--color-text-muted)]">{doctor ? "Reviews your alerts and ECG." : "Your organisation will assign one."}</p>
                </Card>
              </div>
              <SectionTitle actions={<Link className="text-sm text-[var(--color-info)] underline" href="/patient/alerts">All your alerts</Link>}>Latest alerts</SectionTitle>
              <Loaded resource={latest} label="Loading your alerts">
                {(alerts) => (
                  <AlertTable
                    alerts={alerts}
                    detailHref={(a) => segmentHref(a.segment_id)}
                    acknowledgedBy={acknowledger(people)}
                    empty={{ title: "No alerts", description: "Your wearable has not raised any alert." }}
                  />
                )}
              </Loaded>
            </>
          );
        }}
      </Loaded>
    </section>
  );
}

export function PatientAlerts() {
  const { data } = useData();
  const names = useResource(() => loadPeople(data.directory), []);
  const resource = useResource(() => data.care.alerts({ limit: ALERT_LIMIT }), []);
  usePolling(resource.reload, ALERT_POLL_MS);
  const people = names.status === "ready" ? names.data.people : [];
  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <PageIntro title="Alerts" description="Every alert your wearable raised, and whether your doctor has reviewed it. Open one to see its ECG." />
      <MedicalNotice />
      <Loaded resource={resource} label="Loading your alerts">
        {(alerts) => (
          <AlertTable
            alerts={alerts}
            detailHref={(a) => segmentHref(a.segment_id)}
            acknowledgedBy={acknowledger(people)}
            empty={{ title: "No alerts", description: "Your wearable has not raised any alert." }}
          />
        )}
      </Loaded>
    </section>
  );
}

export function PatientRecordings() {
  const { data, session } = useData();
  const patientId = session.patientId;
  // /me names the patient record of a patient's account; without one there is no ECG to show.
  const resource = useResource(() => (patientId ? data.care.segments(patientId) : Promise.reject(new ApiError(404, "no patient record"))), [patientId]);
  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <PageIntro title="ECG Recordings" description="Your ECG: the segments behind alerts, and recordings your doctor requested." />
      <Loaded resource={resource} label="Loading your ECG">
        {(segments) => <SegmentTable segments={segments} href={(s) => `/patient/ecg/${s.segment_id}`} />}
      </Loaded>
    </section>
  );
}
