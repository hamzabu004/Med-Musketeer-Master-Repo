"use client";

import Link from "next/link";
import type { Alert, OrgDevice, PatientSummary, Person } from "@/api/types";
import { useData } from "@/auth/session";
import { Metric, SectionTitle } from "@/components/ui/metric";
import { Notice } from "@/components/ui/notice";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { formatDateTime } from "@/lib/date-time";
import { beatLabel } from "@/lib/labels";
import { loadPeople } from "@/lib/people";
import { useResource } from "@/lib/use-resource";
import { AlertTable } from "../care/alert-table";
import { ALERT_POLL_MS, usePolling } from "../care/use-polling";
import { useCareNames } from "./care-context";
import { useAcknowledge } from "./use-acknowledge";

/** A wearable heard from this recently counts as reporting: a fact about the data, not a verdict on the device. */
const RECENT_MS = 15 * 60_000;

export function DoctorDashboard() {
  const { data } = useData();
  const resource = useResource(async () => {
    const [open, patients, devices, { people }] = await Promise.all([
      data.care.alerts({ unacknowledged: true, limit: 1000 }), data.patients(), data.devices(), loadPeople(data.directory),
    ]);
    return { open, patients, devices, people };
  }, []);
  usePolling(resource.reload, ALERT_POLL_MS);
  const { acknowledge, busy, notice } = useAcknowledge(resource.reload);

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Dashboard" description="What needs your attention: unacknowledged alerts of your patients, and whether their wearables are sending." />
      <Notice notice={notice} />
      <Loaded resource={resource} label="Loading your patients">
        {(loaded, { fetchedAt }) => <Body {...loaded} fetchedAt={fetchedAt} onAcknowledge={acknowledge} busy={busy} />}
      </Loaded>
    </section>
  );
}

function Body({ open, patients, devices, people, fetchedAt, onAcknowledge, busy }: {
  open: Alert[]; patients: PatientSummary[]; devices: OrgDevice[]; people: Person[]; fetchedAt: number;
  onAcknowledge: (alert: Alert) => void; busy: boolean;
}) {
  const names = useCareNames(patients, people);
  const wearables = devices.filter((d) => d.type === "wearable");
  const recent = wearables.filter((d) => d.last_seen && fetchedAt - Date.parse(d.last_seen) < RECENT_MS).length;
  const high = open.filter((a) => a.severity === "high").length;
  const labels = [...new Set(open.map((a) => a.label))];
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Unacknowledged alerts" value={open.length} detail={`${high} high severity`} />
        <Metric label="Patients" value={patients.length} detail={`${patients.filter((p) => !p.wearable_id).length} without a wearable`} />
        <Metric label="Wearables heard from" value={`${recent} / ${wearables.length}`} detail="in the last 15 minutes" />
        <Metric label="Open classifications" value={labels.length} detail={labels.map(beatLabel).join(", ") || "None"} />
      </div>
      <SectionTitle actions={<Link className="text-sm text-[var(--color-info)] underline" href="/doctor/alerts">All alerts</Link>}>
        Unacknowledged alerts
      </SectionTitle>
      <p className="text-xs text-[var(--color-text-muted)]">Updated {formatDateTime(new Date(fetchedAt).toISOString())}; checks again every {ALERT_POLL_MS / 1000} s.</p>
      <AlertTable
        alerts={open.slice(0, 10)}
        patientName={names.patient}
        detailHref={(a) => `/doctor/alerts/${a.alert_id}`}
        acknowledgedBy={names.person}
        onAcknowledge={onAcknowledge}
        busy={busy}
        empty={{ title: "Nothing to acknowledge", description: "All alerts of your patients have been reviewed." }}
      />
      {open.length > 10 && <p className="text-sm"><Link href="/doctor/alerts" className="text-[var(--color-info)] underline">{open.length - 10} more unacknowledged</Link></p>}
    </>
  );
}
