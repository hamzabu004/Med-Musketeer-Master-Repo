"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { Account, NewAccount, PatientSummary } from "@/api/types";
import { useData } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmButton } from "@/components/ui/confirm-button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select, TextInput } from "@/components/ui/form";
import { Notice } from "@/components/ui/notice";
import { OneTimeCode } from "@/components/ui/one-time-code";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Status, statusTone } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatDateTime } from "@/lib/date-time";
import { labelize } from "@/lib/labels";
import { loadPeople, NAMES_UNAVAILABLE, peopleById, personName } from "@/lib/people";
import { useAction } from "@/lib/use-action";
import { useResource } from "@/lib/use-resource";

type Invite = { account: NewAccount; recipient: string };
type Role = "doctor" | "patient";
const EMPTY = { email: "", given_name: "", family_name: "", pseudonym: "" };

/** `role` lives in Accounts: the form unmounts while an invite code is shown, and the next account
 * is usually of the same role (several patients in a row). */
function CreateAccount({ role, onRole, onCreated }: { role: Role; onRole: (role: Role) => void; onCreated: (invite: Invite) => void }) {
  const { data } = useData();
  const { busy, notice, run } = useAction();
  const [form, setForm] = useState(EMPTY);
  const patient = role === "patient";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const body = {
      role,
      email: form.email.trim(),
      given_name: form.given_name.trim(),
      family_name: form.family_name.trim(),
      // The API requires a pseudonym for a patient and refuses one for a doctor.
      pseudonym: patient ? form.pseudonym.trim() : null,
    };
    const account = await run("create", () => data.org.createAccount(body));
    if (account) {
      onCreated({ account, recipient: `${body.given_name} ${body.family_name} (${body.email})` });
    }
  }

  return (
    <Card className="space-y-3 p-4">
      <h3 className="font-semibold">New account</h3>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Role">
          <Select value={role} onChange={(e) => onRole(e.target.value as Role)}>
            <option value="doctor">Doctor</option>
            <option value="patient">Patient</option>
          </Select>
        </Field>
        <Field label="Given name">
          <TextInput value={form.given_name} onChange={(e) => setForm({ ...form, given_name: e.target.value })} required maxLength={200} />
        </Field>
        <Field label="Family name">
          <TextInput value={form.family_name} onChange={(e) => setForm({ ...form, family_name: e.target.value })} required maxLength={200} />
        </Field>
        <Field label="E-mail" hint="Also their user name at sign-in.">
          <TextInput type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required maxLength={254} />
        </Field>
        {patient && (
          <Field label="Pseudonym" hint="How clinical records name the patient, such as P-1004. Unique in your organisation.">
            <TextInput value={form.pseudonym} onChange={(e) => setForm({ ...form, pseudonym: e.target.value })} required maxLength={64} spellCheck={false} />
          </Field>
        )}
        <div className="flex items-end">
          <Button type="submit" disabled={busy !== null}>
            {busy ? "Creating…" : "Create"}
          </Button>
        </div>
      </form>
      <p className="text-xs text-[var(--color-text-muted)]">
        The account gets a one-time invite code; they redeem it at sign-in and choose a password. Organisation administrators are created by the system administrator.
      </p>
      <Notice notice={notice} />
    </Card>
  );
}

export function disableConsequences(account: Account, patients: PatientSummary[]): string[] {
  if (account.role === "doctor") {
    const theirs = patients.filter((p) => p.doctor_id === account.user_id).map((p) => p.pseudonym);
    return [
      "They are signed out and refused from now on.",
      theirs.length
        ? `Their ${theirs.length === 1 ? "patient" : `${theirs.length} patients`} (${theirs.join(", ")}) lose their doctor; no one sees their alerts until you assign another.`
        : "They have no patients at the moment.",
      "This cannot be undone from the dashboard.",
    ];
  }
  const patient = patients.find((p) => p.user_id === account.user_id);
  return [
    "They are signed out and refused from now on.",
    patient?.wearable_id ? "Their wearable is returned and monitoring ends: data it sends afterwards is not theirs." : "They have no wearable issued.",
    "Their records are kept, but no doctor can be assigned and no wearable issued while the account is disabled.",
    "This cannot be undone from the dashboard.",
  ];
}

export function Accounts() {
  const { data } = useData();
  const { busy, notice, run } = useAction();
  // Held above <Loaded>: the code is returned once, so a failed reload must not unmount it.
  const [invite, setInvite] = useState<Invite | null>(null);
  const [role, setRole] = useState<Role>("doctor");
  const [filter, setFilter] = useState({ role: "", status: "" });
  const resource = useResource(async () => {
    const [accounts, patients, { people, named }] = await Promise.all([data.org.accounts(), data.patients(), loadPeople(data.directory)]);
    return { accounts, patients, people, named };
  }, []);

  const loaded = resource.status === "ready" ? resource.data : null;
  const shown = useMemo(
    () => loaded?.accounts.filter((a) => (!filter.role || a.role === filter.role) && (!filter.status || a.status === filter.status)) ?? [],
    [loaded, filter],
  );

  async function disable(account: Account, name: string) {
    if (await run(`disable-${account.user_id}`, () => data.org.disableAccount(account.user_id), `${name}'s account is disabled.`)) resource.reload();
  }

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Accounts" description="Doctors and patients of your organisation, and its administrators. Accounts are created here and disabled here; names and passwords live in the identity provider." />
      {invite ? (
        <OneTimeCode code={invite.account.invite_code} recipient={invite.recipient} onDone={() => setInvite(null)} />
      ) : (
        <CreateAccount
          role={role}
          onRole={setRole}
          onCreated={(created) => {
            setInvite(created);
            resource.reload();
          }}
        />
      )}
      <Notice notice={notice} />
      <div className="grid gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:grid-cols-2 lg:max-w-xl">
        <Field label="Role">
          <Select value={filter.role} onChange={(e) => setFilter({ ...filter, role: e.target.value })}>
            <option value="">All roles</option>
            <option value="doctor">Doctors</option>
            <option value="patient">Patients</option>
            <option value="org_admin">Administrators</option>
          </Select>
        </Field>
        <Field label="Status">
          <Select value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="disabled">Disabled</option>
          </Select>
        </Field>
      </div>
      <Loaded resource={resource} label="Loading accounts">
        {({ patients, people, named }) => {
          const byId = peopleById(people);
          return (
            <>
              {!named && <p className="text-xs text-[var(--color-text-muted)]">{NAMES_UNAVAILABLE}</p>}
              {shown.length ? (
                <Table label="Accounts" minWidth={860}>
                  <THead columns={["Name", "E-mail", "Role", "Patient", "Status", "Created", ""]} />
                  <tbody>
                    {shown.map((a) => {
                      const person = byId.get(a.user_id);
                      const name = personName(person);
                      return (
                        <Tr key={a.user_id}>
                          <Td className="font-medium">{name ?? <RecordId id={a.user_id} />}</Td>
                          <Td className="break-all">{person?.email ?? "—"}</Td>
                          <Td>{labelize(a.role)}</Td>
                          <Td>{a.patient_id ? <Link href={`/org/patients/${a.patient_id}`} className="text-[var(--color-info)]">{a.pseudonym}</Link> : "—"}</Td>
                          <Td><Status label={labelize(a.status)} tone={statusTone(a.status)} /></Td>
                          <Td className="metric-number whitespace-nowrap">{formatDateTime(a.created_at)}</Td>
                          <Td>
                            {/* The API disables doctors and patients only; administrators are managed by the system administrator. */}
                            {a.status === "active" && (a.role === "doctor" || a.role === "patient") && (
                              <ConfirmButton
                                label="Disable"
                                variant="danger"
                                title={`Disable ${name ?? `this ${a.role}`}?`}
                                consequences={disableConsequences(a, patients)}
                                disabled={busy !== null}
                                onConfirm={() => void disable(a, name ?? labelize(a.role))}
                              />
                            )}
                          </Td>
                        </Tr>
                      );
                    })}
                  </tbody>
                </Table>
              ) : (
                <EmptyState title="No accounts match" description="Change the filters, or create an account above." />
              )}
            </>
          );
        }}
      </Loaded>
    </section>
  );
}
