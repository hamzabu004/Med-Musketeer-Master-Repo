"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { LabeledSelect } from "@/components/ui/labeled-select";
import { PageIntro } from "@/components/ui/page-intro";
import { displayEmail } from "@/lib/display-identifiers";
import { services } from "@/services";
import type { Role, User } from "@/types";
import { AdminPageError, AdminPageSkeleton } from "./admin-page-state";
import { inputClass, labelize, LabeledStatus, tableClass, tableWrapClass, tdClass, thClass } from "./admin-ui";
import { useAdminOverview } from "./use-admin-overview";

type Row = { id: string; name: string; identifier: string; type: "patient" | "doctor" | "administrator" | "wearable" | "monitoring-station"; status: string; user?: User; actionHref?: string };

export function AdminIdentities() {
  const { state, refresh } = useAdminOverview();
  const [query, setQuery] = useState("");
  const [type, setType] = useState("all");
  const [draft, setDraft] = useState<User | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  if (state.status === "loading") return <AdminPageSkeleton />;
  if (state.status === "error") return <AdminPageError message={state.message} onRetry={refresh} />;
  const data = state.data;
  const rows: Row[] = [
    ...data.users.map((user): Row => ({ id: user.id, name: user.displayName, identifier: displayEmail(user.email), type: user.role === "admin" ? "administrator" : user.role, status: user.status, user })),
    ...data.devices.map((device): Row => ({ id: device.id, name: device.id, identifier: device.identity ?? "Identity not set", type: "wearable", status: device.status, actionHref: "/admin/devices" })),
    ...data.stations.map((station): Row => ({ id: station.id, name: station.name, identifier: station.ipAddress ?? "Network field not set", type: "monitoring-station", status: station.status, actionHref: "/admin/monitoring-stations" })),
  ].filter((row) => (type === "all" || row.type === type) && `${row.name} ${row.identifier} ${row.id}`.toLowerCase().includes(query.toLowerCase()));

  function createUser() {
    const next = String(data.users.length + 1).padStart(3, "0");
    setDraft({ id: `USR-M-${next}`, organizationId: data.session.organizationId, email: "", role: "patient", displayName: "", status: "active" });
  }

  async function saveUser(event: React.FormEvent) {
    event.preventDefault();
    if (!draft) return;
    const fixedAccount = data.users.find((user) => user.id === draft.id);
    const record = fixedAccount ? { ...draft, email: fixedAccount.email, role: fixedAccount.role } : draft;
    if (data.users.some((user) => user.email.toLowerCase() === record.email.toLowerCase() && user.id !== record.id)) {
      setMessage("That identity email is already present in browser state.");
      return;
    }
    setSavingId(draft.id);
    await services.identities.saveUser(data.session.organizationId, record);
    setMessage(`${record.displayName} saved in browser state. Fixed sign-in identifiers and roles remain unchanged.`);
    setDraft(null);
    setSavingId(null);
    refresh();
  }

  async function toggle(user: User) {
    setSavingId(user.id); setMessage("");
    try {
      await services.identities.saveUser(data.session.organizationId, { ...user, status: user.status === "active" ? "disabled" : "active" });
      setMessage(`${user.displayName} updated in browser state.`); setSavingId(null); refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Identity update failed."); setSavingId(null);
    }
  }

  return <section className="mx-auto max-w-[1450px] space-y-5">
    <PageIntro title="Users & Identity" description="Simulated identity inventory. This screen does not provide production identity or credential management." actions={<Button type="button" onClick={createUser}>Create user identity</Button>} />
    <div className="grid gap-3 sm:grid-cols-2"><label className="block text-sm font-medium">Search identities<input className={inputClass} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, ID, or identifier" /></label><LabeledSelect label="Identity type" value={type} onChange={(event) => setType(event.target.value)}><option value="all">All identities</option><option value="patient">Patient users</option><option value="doctor">Clinicians</option><option value="administrator">Organization Administrators</option><option value="wearable">Wearables</option><option value="monitoring-station">Monitoring Stations</option></LabeledSelect></div>
    {message && <p role="status" className="border-l-2 border-[var(--color-accent)] bg-[var(--color-accent-soft)] px-3 py-2 text-sm">{message}</p>}
    {!rows.length ? <EmptyState title="No identities found" description="No identities match the current filters." /> : <div className={tableWrapClass}><table className={tableClass}><thead className="bg-[var(--color-surface-subtle)] text-[var(--color-text-muted)]"><tr>{["Identity", "Type / role", "Identifier", "Status", "Actions"].map((heading) => <th className={thClass} key={heading}>{heading}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={`${row.type}-${row.id}`} className="border-t border-[var(--color-border)]"><td className={tdClass}><span className="font-medium">{row.name}</span><br /><span className="text-xs text-[var(--color-text-muted)]">{row.id}</span></td><td className={tdClass}>{labelize(row.type)}</td><td className={tdClass}>{row.identifier}</td><td className={tdClass}><LabeledStatus value={row.status} /></td><td className={`${tdClass} whitespace-nowrap`}>{row.user ? <div className="flex gap-2"><Button type="button" variant="secondary" onClick={() => setDraft(structuredClone(row.user!))}>Edit</Button><Button type="button" variant="secondary" disabled={savingId === row.id || row.user.id === data.session.userId} onClick={() => void toggle(row.user!)}>{row.user.status === "active" ? "Disable" : "Activate"}</Button><Button type="button" variant="secondary" onClick={() => setMessage(`Credential reset simulated for ${row.user!.displayName}; fixed sign-in accounts remain unchanged.`)}>Reset credential</Button></div> : <Link className="font-medium text-[var(--color-info)] underline-offset-2 hover:underline" href={row.actionHref!}>Manage</Link>}</td></tr>)}</tbody></table></div>}
    {draft && <Card className="p-5"><h3 className="font-semibold">{data.users.some((user) => user.id === draft.id) ? "Edit" : "Create"} user identity</h3><form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={(event) => void saveUser(event)}><label className="text-sm font-medium">Display name<input className={inputClass} value={draft.displayName} onChange={(event) => setDraft({ ...draft, displayName: event.target.value })} required /></label><label className="text-sm font-medium">Email identifier<input className={inputClass} type="email" value={displayEmail(draft.email)} onChange={(event) => setDraft({ ...draft, email: event.target.value })} required /></label><label className="text-sm font-medium">Role<select className={inputClass} value={draft.role} onChange={(event) => setDraft({ ...draft, role: event.target.value as Role })}><option value="patient">Patient</option><option value="doctor">Doctor</option><option value="admin">Organization Administrator</option></select></label><label className="text-sm font-medium">Status<select className={inputClass} value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value as User["status"] })}><option value="active">Active</option><option value="disabled">Disabled</option></select></label><div className="flex gap-2 sm:col-span-2"><Button type="submit" disabled={savingId === draft.id}>Save identity</Button><Button type="button" variant="secondary" onClick={() => setDraft(null)}>Cancel</Button></div></form></Card>}
    <p className="text-xs text-[var(--color-text-muted)]">Credential reset is a labeled simulation only. Wearable and Monitoring Station identity assignments are managed on their dedicated screens. The signed-in administrator cannot disable itself.</p>
  </section>;
}
