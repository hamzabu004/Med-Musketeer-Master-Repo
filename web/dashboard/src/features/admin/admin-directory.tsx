"use client";

import { useState } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageIntro } from "@/components/ui/page-intro";
import { formatDateTime } from "@/lib/date-time";
import { AdminPageError, AdminPageSkeleton } from "./admin-page-state";
import { inputClass, LabeledStatus, tableClass, tableWrapClass, tdClass, thClass } from "./admin-ui";
import { useAdminOverview } from "./use-admin-overview";

export function AdminPatients() {
  const { state, refresh } = useAdminOverview();
  const [query, setQuery] = useState("");
  if (state.status === "loading") return <AdminPageSkeleton />;
  if (state.status === "error") return <AdminPageError message={state.message} onRetry={refresh} />;
  const { patients, doctors, devices, stations, users } = state.data;
  const rows = patients.filter((patient) => `${patient.displayName} ${patient.id}`.toLowerCase().includes(query.toLowerCase()));
  return <section className="mx-auto max-w-7xl space-y-5"><PageIntro title="Patient Management" description="Patient assignments and account linkage in the deterministic dataset." />
    <label className="block max-w-sm text-sm font-medium">Search patients<input className={inputClass} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name or patient ID" /></label>
    {!rows.length ? <EmptyState title="No patients found" description="No patient records match the current search." /> : <div className={tableWrapClass}><table className={tableClass}><thead className="bg-[var(--color-surface-subtle)] text-[var(--color-text-muted)]"><tr>{["Patient","Clinician","Wearable","Monitoring Station","Account","Last update"].map((h)=><th className={thClass} key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((patient)=>{
      const account=users.find((u)=>u.id===patient.userId); const device=devices.find((d)=>d.id===patient.deviceId); const station=stations.find((s)=>s.id===patient.monitoringStationId);
      return <tr className="border-t border-[var(--color-border)]" key={patient.id}><td className={tdClass}><span className="font-medium">{patient.displayName}</span><br/><span className="text-xs text-[var(--color-text-muted)]">{patient.id}</span></td><td className={tdClass}>{patient.assignedDoctorIds.map((id)=>doctors.find((d)=>d.id===id)?.displayName ?? id).join(", ") || "Unassigned"}</td><td className={tdClass}>{device ? <><span>{device.id}</span><br/><LabeledStatus value={device.status}/></> : "Unassigned"}</td><td className={tdClass}>{station?.name ?? "Unassigned"}</td><td className={tdClass}>{account ? <LabeledStatus value={account.status}/> : <span className="text-[var(--color-text-muted)]">No linked sign-in</span>}</td><td className={`${tdClass} metric-number`}>{formatDateTime(patient.lastUpdatedAt)}</td></tr>;
    })}</tbody></table></div>}</section>;
}

export function AdminClinicians() {
  const { state, refresh } = useAdminOverview();
  if (state.status === "loading") return <AdminPageSkeleton />;
  if (state.status === "error") return <AdminPageError message={state.message} onRetry={refresh} />;
  const { doctors, users, stations } = state.data;
  return <section className="mx-auto max-w-7xl space-y-5"><PageIntro title="Clinician Management" description="Clinician accounts and deterministic monitoring assignments. Changes here are simulated only." />
    {!doctors.length ? <EmptyState title="No clinicians" description="No clinician identities are present in browser state."/> : <div className={tableWrapClass}><table className={tableClass}><thead className="bg-[var(--color-surface-subtle)] text-[var(--color-text-muted)]"><tr>{["Clinician","Account","Registered patients","Monitoring Stations","Actions"].map((h)=><th className={thClass} key={h}>{h}</th>)}</tr></thead><tbody>{doctors.map((doctor)=>{const user=users.find((u)=>u.id===doctor.userId); return <tr className="border-t border-[var(--color-border)]" key={doctor.id}><td className={tdClass}><span className="font-medium">{doctor.displayName}</span><br/><span className="text-xs text-[var(--color-text-muted)]">{doctor.id}</span></td><td className={tdClass}>{user ? <LabeledStatus value={user.status}/> : "Not linked"}</td><td className={`${tdClass} metric-number`}>{doctor.patientIds.length}</td><td className={tdClass}>{doctor.monitoringStationIds.map((id)=>stations.find((s)=>s.id===id)?.name ?? id).join(", ") || "None"}</td><td className={tdClass}><Link className="font-medium text-[var(--color-info)] underline-offset-2 hover:underline" href="/admin/identities">Manage identity</Link></td></tr>})}</tbody></table></div>}
  </section>;
}
