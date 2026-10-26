"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useData } from "@/auth/session";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select, TextInput } from "@/components/ui/form";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Status, statusTone } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { labelize } from "@/lib/labels";
import { loadPeople, NAMES_UNAVAILABLE, peopleById, personName } from "@/lib/people";
import { useResource } from "@/lib/use-resource";

export function Patients() {
  const { data } = useData();
  const [filter, setFilter] = useState({ query: "", show: "" });
  const resource = useResource(async () => {
    const [patients, { people, named }] = await Promise.all([data.patients(), loadPeople(data.directory)]);
    return { patients, people, named };
  }, []);

  const loaded = resource.status === "ready" ? resource.data : null;
  const rows = useMemo(() => {
    if (!loaded) return [];
    const byId = peopleById(loaded.people);
    const query = filter.query.trim().toLowerCase();
    return loaded.patients
      .map((p) => ({ patient: p, name: p.user_id ? personName(byId.get(p.user_id)) : null, doctor: p.doctor_id ? personName(byId.get(p.doctor_id)) : null }))
      .filter(({ patient: p, name }) => {
        if (query && !p.pseudonym.toLowerCase().includes(query) && !name?.toLowerCase().includes(query)) return false;
        if (filter.show === "no_doctor") return p.account_status === "active" && !p.doctor_id;
        if (filter.show === "no_wearable") return p.account_status === "active" && !p.wearable_id;
        if (filter.show === "disabled") return p.account_status !== "active";
        return true;
      });
  }, [loaded, filter]);

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Patients" description="Every patient of your organisation, with their doctor and wearable. Create a patient on the Accounts page." />
      <div className="grid gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:grid-cols-2 lg:max-w-2xl">
        <Field label="Search">
          <TextInput value={filter.query} onChange={(e) => setFilter({ ...filter, query: e.target.value })} placeholder="Pseudonym or name" />
        </Field>
        <Field label="Show">
          <Select value={filter.show} onChange={(e) => setFilter({ ...filter, show: e.target.value })}>
            <option value="">All patients</option>
            <option value="no_doctor">Without a doctor</option>
            <option value="no_wearable">Without a wearable</option>
            <option value="disabled">Disabled accounts</option>
          </Select>
        </Field>
      </div>
      <Loaded resource={resource} label="Loading patients">
        {({ named }) => (
          <>
            {!named && <p className="text-xs text-[var(--color-text-muted)]">{NAMES_UNAVAILABLE}</p>}
            {rows.length ? (
              <Table label="Patients" minWidth={760}>
                <THead columns={["Pseudonym", "Name", "Doctor", "Wearable", "Account"]} />
                <tbody>
                  {rows.map(({ patient: p, name, doctor }) => (
                    <Tr key={p.patient_id}>
                      <Td>
                        <Link href={`/org/patients/${p.patient_id}`} className="font-medium text-[var(--color-info)] underline-offset-2 hover:underline">{p.pseudonym}</Link>
                      </Td>
                      <Td>{name ?? "—"}</Td>
                      <Td>{p.doctor_id ? (doctor ?? <RecordId id={p.doctor_id} />) : <span className="text-[var(--color-warning)]">None</span>}</Td>
                      <Td>{p.wearable_id ? <RecordId id={p.wearable_id} /> : <span className="text-[var(--color-text-muted)]">None</span>}</Td>
                      <Td><Status label={labelize(p.account_status ?? "none")} tone={statusTone(p.account_status)} /></Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="No patients match" description="Change the search or the filter. New patients are created on the Accounts page." />
            )}
          </>
        )}
      </Loaded>
    </section>
  );
}
