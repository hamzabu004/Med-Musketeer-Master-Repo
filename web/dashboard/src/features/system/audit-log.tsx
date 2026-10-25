"use client";

import { useState } from "react";
import { useData } from "@/auth/session";
import { Field, Select } from "@/components/ui/form";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { useResource } from "@/lib/use-resource";
import { AuditTable } from "./audit-table";

const KINDS = [
  ["", "All changes"],
  ["organisation", "Organisations"],
  ["account", "Accounts"],
  ["device", "Devices"],
  ["credential", "Credentials"],
  ["grant", "Grants"],
] as const;

export function AuditLog() {
  const { data } = useData();
  const resource = useResource(async () => {
    const [events, organisations] = await Promise.all([data.registry.audit(1000), data.registry.organisations()]);
    return { events, organisations };
  }, []);
  const [kind, setKind] = useState("");

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Audit Log" description="Registry changes with who made them. Changes inside an organisation (patients, doctors) are in that organisation's own log." />
      <div className="max-w-xs">
        <Field label="Show">
          <Select value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </Select>
        </Field>
      </div>
      <Loaded resource={resource} label="Loading the audit log">
        {({ events, organisations }) => <AuditTable events={events.filter((e) => !kind || e.action.startsWith(`${kind}.`))} organisations={organisations} />}
      </Loaded>
    </section>
  );
}
