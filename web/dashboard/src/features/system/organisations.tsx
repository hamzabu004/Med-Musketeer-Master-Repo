"use client";

import Link from "next/link";
import { useState } from "react";
import { useData } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select, TextInput } from "@/components/ui/form";
import { Notice } from "@/components/ui/notice";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { Status, statusTone } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatDateTime } from "@/lib/date-time";
import { labelize } from "@/lib/labels";
import { useAction } from "@/lib/use-action";
import { useResource } from "@/lib/use-resource";

function CreateOrganisation({ onCreated }: { onCreated: () => void }) {
  const { data } = useData();
  const { busy, notice, run } = useAction();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"public" | "private">("public");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const created = await run("create", () => data.registry.createOrganisation({ name: name.trim(), kind }), `Organisation "${name.trim()}" created.`);
    if (created) {
      setName("");
      onCreated();
    }
  }

  return (
    <Card className="space-y-3 p-4">
      <h3 className="font-semibold">New organisation</h3>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_12rem_auto] sm:items-end">
        <Field label="Name">
          <TextInput value={name} onChange={(e) => setName(e.target.value)} required maxLength={200} placeholder="e.g. City Hospital" />
        </Field>
        <Field label="Kind">
          <Select value={kind} onChange={(e) => setKind(e.target.value as "public" | "private")}>
            <option value="public">Public</option>
            <option value="private">Private</option>
          </Select>
        </Field>
        <Button type="submit" disabled={busy !== null || !name.trim()}>
          {busy ? "Creating…" : "Create"}
        </Button>
      </form>
      <p className="text-xs text-[var(--color-text-muted)]">Also creates its organisation in ZITADEL, where its people sign in. Add its first administrator on the organisation&apos;s page.</p>
      <Notice notice={notice} />
    </Card>
  );
}

export function Organisations() {
  const { data } = useData();
  const resource = useResource(() => data.registry.organisations(), []);

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <PageIntro title="Organisations" description="Hospitals and clinics using MedMusketeer. Each has its own administrators, doctors, patients and granted devices." />
      <CreateOrganisation onCreated={() => resource.status === "ready" && resource.reload()} />
      <Loaded resource={resource} label="Loading organisations">
        {(organisations) =>
          organisations.length ? (
            <Table label="Organisations" minWidth={640}>
              <THead columns={["Name", "Kind", "Status", "Created"]} />
              <tbody>
                {organisations.map((org) => (
                  <Tr key={org.org_id}>
                    <Td className="font-medium">
                      <Link href={`/system/organisations/${org.org_id}`} className="text-[var(--color-info)] underline-offset-2 hover:underline">
                        {org.name}
                      </Link>
                    </Td>
                    <Td>{labelize(org.kind)}</Td>
                    <Td><Status label={labelize(org.status)} tone={statusTone(org.status)} /></Td>
                    <Td className="metric-number">{formatDateTime(org.created_at)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState title="No organisations yet" description="Create the first one above." />
          )
        }
      </Loaded>
    </section>
  );
}
