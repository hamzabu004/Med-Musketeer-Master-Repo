"use client";

import { useState } from "react";
import { useData } from "@/auth/session";
import { Field, Select } from "@/components/ui/form";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { loadPeople, NAMES_UNAVAILABLE } from "@/lib/people";
import { useResource } from "@/lib/use-resource";
import { OrgAuditTable } from "./org-audit-table";

/** The API's largest page of audit rows. */
export const AUDIT_LIMIT = 1000;

const KINDS = [
  ["", "All changes"],
  ["account", "Accounts"],
  ["doctor", "Doctor assignments"],
  ["wearable", "Wearables"],
  ["disorder", "Disorders"],
  ["patient", "Exports"],
  ["grant", "Device grants"],
  ["organisation", "Organisation"],
] as const;

export function OrgAuditLog() {
  const { data } = useData();
  const [kind, setKind] = useState("");
  const resource = useResource(async () => {
    const [events, patients, { people, named }] = await Promise.all([data.org.audit(AUDIT_LIMIT), data.patients(), loadPeople(data.directory)]);
    return { events, patients, people, named };
  }, []);

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro
        title="Audit Log"
        description="Every change in your organisation and who made it, including the system administrator's grants and status changes."
      />
      <div className="max-w-xs">
        <Field label="Show">
          <Select value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </Select>
        </Field>
      </div>
      <Loaded resource={resource} label="Loading the audit log">
        {({ events, patients, people, named }) => (
          <>
            {!named && <p className="text-xs text-[var(--color-text-muted)]">{NAMES_UNAVAILABLE}</p>}
            <OrgAuditTable events={events.filter((e) => !kind || e.action.startsWith(`${kind}.`))} patients={patients} people={people} />
            {events.length >= AUDIT_LIMIT && <p className="text-xs text-[var(--color-text-muted)]">Showing the newest {AUDIT_LIMIT} changes.</p>}
          </>
        )}
      </Loaded>
    </section>
  );
}
