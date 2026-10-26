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
import { useResource } from "@/lib/use-resource";
import { AlertTable } from "../care/alert-table";
import { ALERT_LIMIT, countLabel } from "../care/limits";
import { ALERT_POLL_MS, usePolling } from "../care/use-polling";
import { useCareContext, useCareNames } from "./care-context";
import { useAcknowledge } from "./use-acknowledge";

/** A wearable heard from this recently counts as reporting: a fact about the data, not a verdict on the device. */
const RECENT_MS = 15 * 60_000;
const SHOWN = 10;

export function DoctorDashboard() {
  const { data } = useData();
  const context = useCareContext();
  const open = useResource(() => data.care.alerts({ unacknowledged: true, limit: ALERT_LIMIT }), []);
  usePolling(open.reload, ALERT_POLL_MS);
  const { acknowledge, isPending, notice } = useAcknowledge(open.reload);

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Dashboard" description="What needs your attention: unacknowledged alerts of your patients, and whether their wearables are sending." />
      <Notice notice={notice} />
      <Loaded resource={context} label="Loading your patients">
        {({ patients, devices, people }) => (
          <Loaded resource={open} label="Loading alerts">
            {(alerts, { fetchedAt }) => (
              <Body open={alerts} patients={patients} devices={devices} people={people} fetchedAt={fetchedAt} onAcknowledge={acknowledge} isPending={isPending} />
            )}
          </Loaded>
        )}
      </Loaded>
    </section>
  );
}

function Body({ open, patients, devices, people, fetchedAt, onAcknowledge, isPending }: {
  open: Alert[]; patients: PatientSummary[]; devices: OrgDevice[]; people: Person[]; fetchedAt: number;
  onAcknowledge: (alert: Alert) => void; isPending: (alert: Alert) => boolean;
}) {
  const names = useCareNames(patients, people);
  const wearables = devices.filter((d) => d.type === "wearable");
  const recent = wearables.filter((d) => d.last_seen && fetchedAt - Date.parse(d.last_seen) < RECENT_MS).length;
  const high = open.filter((a) => a.severity === "high" || a.severity === "critical").length;
  const labels = [...new Set(open.map((a) => a.label))];
  const full = open.length >= ALERT_LIMIT;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Unacknowledged alerts" value={countLabel(open.length)} detail={`${countLabel(high)} high severity${full ? ", among the newest 1000" : ""}`} />
        <Metric label="Patients" value={patients.length} detail={`${patients.filter((p) => !p.wearable_id).length} without a wearable`} />
        <Metric label="Wearables heard from" value={`${recent} / ${wearables.length}`} detail="in the last 15 minutes" />
        <Metric label="Open classifications" value={labels.length} detail={labels.map(beatLabel).join(", ") || "None"} />
      </div>
      <SectionTitle actions={<Link className="text-sm text-[var(--color-info)] underline" href="/doctor/alerts">All alerts</Link>}>
        Unacknowledged alerts
      </SectionTitle>
      <p className="text-xs text-[var(--color-text-muted)]">Updated {formatDateTime(new Date(fetchedAt).toISOString())}; checks again every {ALERT_POLL_MS / 1000} s.</p>
      <AlertTable
        alerts={open.slice(0, SHOWN)}
        patientName={names.patient}
        detailHref={(a) => `/doctor/alerts/${a.alert_id}`}
        acknowledgedBy={names.person}
        onAcknowledge={onAcknowledge}
        isPending={isPending}
        empty={{ title: "Nothing to acknowledge", description: "All alerts of your patients have been reviewed." }}
      />
      {open.length > SHOWN && (
        <p className="text-sm"><Link href="/doctor/alerts" className="text-[var(--color-info)] underline">{full ? "More" : `${open.length - SHOWN} more`} unacknowledged in the inbox</Link></p>
      )}
    </>
  );
}
