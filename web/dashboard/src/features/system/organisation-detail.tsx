"use client";

import Link from "next/link";
import { useState } from "react";
import type { NewAccount } from "@/api/types";
import { ApiError } from "@/api/errors";
import { useData } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmButton } from "@/components/ui/confirm-button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, TextInput } from "@/components/ui/form";
import { SectionTitle } from "@/components/ui/metric";
import { Notice } from "@/components/ui/notice";
import { OneTimeCode } from "@/components/ui/one-time-code";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Status, statusTone } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatAgo, formatDateTime } from "@/lib/date-time";
import { deviceType, labelize } from "@/lib/labels";
import { useAction } from "@/lib/use-action";
import { useResource } from "@/lib/use-resource";

/** The API's largest page of audit rows. */
const AUDIT_LIMIT = 1000;

type Invite = { account: NewAccount; recipient: string };

function CreateAdmin({ orgId, disabled, onCreated }: { orgId: string; disabled: boolean; onCreated: (invite: Invite) => void }) {
  const { data } = useData();
  const { busy, notice, run } = useAction();
  const [form, setForm] = useState({ email: "", given_name: "", family_name: "" });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const body = { email: form.email.trim(), given_name: form.given_name.trim(), family_name: form.family_name.trim() };
    const account = await run("create", () => data.registry.createOrganisationAdmin(orgId, body));
    if (account) {
      setForm({ email: "", given_name: "", family_name: "" });
      onCreated({ account, recipient: `${body.given_name} ${body.family_name} (${body.email})` });
    }
  }

  return (
    <Card className="space-y-3 p-4">
      <h3 className="font-semibold">New organisation administrator</h3>
      {disabled ? (
        <p className="text-sm text-[var(--color-text-muted)]">The organisation is suspended: reactivate it to add administrators.</p>
      ) : (
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1.4fr_auto] lg:items-end">
          <Field label="Given name">
            <TextInput value={form.given_name} onChange={(e) => setForm({ ...form, given_name: e.target.value })} required maxLength={200} />
          </Field>
          <Field label="Family name">
            <TextInput value={form.family_name} onChange={(e) => setForm({ ...form, family_name: e.target.value })} required maxLength={200} />
          </Field>
          <Field label="E-mail">
            <TextInput type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          </Field>
          <Button type="submit" disabled={busy !== null}>
            {busy ? "Creating…" : "Create"}
          </Button>
        </form>
      )}
      <Notice notice={notice} />
    </Card>
  );
}

export function OrganisationDetail({ orgId }: { orgId: string }) {
  const { data } = useData();
  const { busy, notice, run } = useAction();
  // Held above <Loaded>: the code is returned once, so a failed reload must not unmount it.
  const [invite, setInvite] = useState<Invite | null>(null);
  const resource = useResource(async () => {
    const [organisations, devices, audit] = await Promise.all([data.registry.organisations(), data.registry.devices(), data.registry.audit(AUDIT_LIMIT)]);
    const org = organisations.find((o) => o.org_id === orgId);
    if (!org) throw new ApiError(404, "organisation not found");
    // The registry has no grants-by-organisation endpoint: read each device's grants.
    const grants = (await Promise.all(devices.map((d) => data.registry.grants(d.device_id)))).flat();
    const granted = grants.filter((g) => g.org_id === orgId && g.revoked_at === null);
    return {
      org,
      devices: granted.map((g) => ({ grant: g, device: devices.find((d) => d.device_id === g.device_id)! })),
      // No endpoint lists an organisation's administrators to the system admin; the audit log records each one created.
      admins: audit.filter((e) => e.action === "account.created" && e.org_id === orgId && e.details?.role === "org_admin"),
      auditFull: audit.length >= AUDIT_LIMIT,
    };
  }, [orgId]);

  async function setStatus(status: "active" | "suspended") {
    if (await run(status, () => data.registry.setOrganisationStatus(orgId, status), status === "suspended" ? "Organisation suspended." : "Organisation reactivated.")) {
      resource.reload();
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      {invite && <OneTimeCode code={invite.account.invite_code} recipient={invite.recipient} onDone={() => setInvite(null)} />}
      <Loaded resource={resource} label="Loading the organisation">
      {({ org, devices, admins, auditFull }) => (
        <section className="space-y-5">
          <PageIntro
            title={org.name}
            description={`${labelize(org.kind)} organisation, created ${formatDateTime(org.created_at)}.`}
            actions={
              <>
                <Status label={labelize(org.status)} tone={statusTone(org.status)} />
                {org.status === "active" ? (
                  <ConfirmButton
                    label="Suspend"
                    variant="danger"
                    title={`Suspend ${org.name}?`}
                    consequences={[
                      "Everyone in it is refused at once: its administrators, doctors and patients cannot use MedMusketeer until it is reactivated.",
                      "No new accounts can be created in it, and no devices granted to it.",
                      "Accounts, patients, data and grants are kept; reactivating restores access.",
                    ]}
                    disabled={busy !== null}
                    onConfirm={() => void setStatus("suspended")}
                  />
                ) : (
                  <Button type="button" variant="secondary" disabled={busy !== null} onClick={() => void setStatus("active")}>
                    Reactivate
                  </Button>
                )}
              </>
            }
          />
          <Notice notice={notice} />
          <p className="text-sm">
            <Link href="/system/organisations" className="text-[var(--color-info)] underline">All organisations</Link>
          </p>

          {!invite && (
            <CreateAdmin
              orgId={orgId}
              disabled={org.status !== "active"}
              onCreated={(created) => {
                setInvite(created);
                resource.reload();
              }}
            />
          )}

          <SectionTitle>Administrators created</SectionTitle>
          {auditFull && (
            <p className="text-xs text-[var(--color-text-muted)]">Searched the newest {AUDIT_LIMIT} registry changes only; administrators created before them are not listed.</p>
          )}
          {admins.length ? (
            <Table label="Administrators created" minWidth={480}>
              <THead columns={["Account", "Created"]} />
              <tbody>
                {admins.map((event) => (
                  <Tr key={event.event_id}>
                    <Td><RecordId id={event.target_id} /></Td>
                    <Td className="metric-number">{formatDateTime(event.at)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState title="No administrator recorded" description="Administrators created from this dashboard appear here, from the registry audit log. Names stay with the organisation." />
          )}

          <SectionTitle>Devices granted</SectionTitle>
          {devices.length ? (
            <Table label="Devices granted" minWidth={640}>
              <THead columns={["Device", "Type", "Status", "Last seen", "Granted"]} />
              <tbody>
                {devices.map(({ grant, device }) => (
                  <Tr key={grant.grant_id}>
                    <Td><Link href={`/system/devices/${device.device_id}`} className="text-[var(--color-info)]"><RecordId id={device.device_id} /></Link></Td>
                    <Td>{deviceType(device.type)}</Td>
                    <Td><Status label={labelize(device.status)} tone={statusTone(device.status)} /></Td>
                    <Td>{formatAgo(device.last_seen)}</Td>
                    <Td className="metric-number">{formatDateTime(grant.granted_at)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState title="No devices granted" description="Grant a device to this organisation from the device's page." />
          )}
        </section>
      )}
      </Loaded>
    </div>
  );
}
