"use client";

import { useState } from "react";
import type { Alert, PatientSummary, Person } from "@/api/types";
import { useData } from "@/auth/session";
import { Field, Select } from "@/components/ui/form";
import { Notice } from "@/components/ui/notice";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { formatDateTime } from "@/lib/date-time";
import { useResource } from "@/lib/use-resource";
import { AlertTable, severityTone } from "../care/alert-table";
import { ALERT_LIMIT, countLabel } from "../care/limits";
import { ALERT_POLL_MS, usePolling } from "../care/use-polling";
import { useAcknowledge } from "./use-acknowledge";
import { useCareContext, useCareNames } from "./care-context";

export function DoctorAlerts() {
  const { data } = useData();
  const [show, setShow] = useState<"open" | "all">("open");
  const [severity, setSeverity] = useState("");
  const [openedAt] = useState(() => Date.now());
  const context = useCareContext();
  const alerts = useResource(() => data.care.alerts({ unacknowledged: show === "open", limit: ALERT_LIMIT }), [show]);
  usePolling(alerts.reload, ALERT_POLL_MS);
  const { acknowledge, isPending, notice } = useAcknowledge(alerts.reload);

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Alerts" description="Alerts of your patients, newest first. Acknowledge each one once you have reviewed it; every alert needs a doctor's acknowledgement." />
      <div className="grid gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:grid-cols-2 lg:max-w-xl">
        <Field label="Show">
          <Select value={show} onChange={(e) => setShow(e.target.value as "open" | "all")}>
            <option value="open">Unacknowledged</option>
            <option value="all">All alerts</option>
          </Select>
        </Field>
        <Field label="Severity">
          <Select value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">All severities</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </Select>
        </Field>
      </div>
      <Notice notice={notice} />
      <Loaded resource={context} label="Loading your patients">
        {({ patients, people }) => (
          <Loaded resource={alerts} label="Loading alerts">
            {(list, { fetchedAt }) => (
              <Inbox alerts={list} patients={patients} people={people} fetchedAt={fetchedAt} severity={severity} openedAt={openedAt} onAcknowledge={acknowledge} isPending={isPending} />
            )}
          </Loaded>
        )}
      </Loaded>
    </section>
  );
}

/** The severity filter: "high" includes any value shown as critical (severity is free text). */
function matches(alert: Alert, severity: string): boolean {
  if (!severity) return true;
  return severity === "high" ? severityTone(alert.severity) === "critical" : alert.severity === severity;
}

function Inbox({ alerts, patients, people, fetchedAt, severity, openedAt, onAcknowledge, isPending }: {
  alerts: Alert[];
  patients: PatientSummary[];
  people: Person[];
  fetchedAt: number;
  severity: string;
  openedAt: number;
  onAcknowledge: (alert: Alert) => void;
  isPending: (alert: Alert) => boolean;
}) {
  const names = useCareNames(patients, people);
  const shown = alerts.filter((a) => matches(a, severity));
  const fresh = alerts.filter((a) => !a.acknowledged_at && Date.parse(a.created_at) > openedAt).length;
  return (
    <>
      <p className="text-xs text-[var(--color-text-muted)]" aria-live="polite">
        {fresh > 0 && <strong className="mr-2 text-[var(--color-critical)]">{fresh} new since you opened this page.</strong>}
        {countLabel(alerts.length)} {alerts.length === 1 ? "alert" : "alerts"}. Updated {formatDateTime(new Date(fetchedAt).toISOString())}; checks again every {ALERT_POLL_MS / 1000} s.
      </p>
      <AlertTable
        alerts={shown}
        patientName={names.patient}
        detailHref={(a) => `/doctor/alerts/${a.alert_id}`}
        acknowledgedBy={names.person}
        onAcknowledge={onAcknowledge}
        isPending={isPending}
        empty={{ title: "Nothing to acknowledge", description: "New alerts of your patients appear here within seconds of arriving." }}
      />
    </>
  );
}
