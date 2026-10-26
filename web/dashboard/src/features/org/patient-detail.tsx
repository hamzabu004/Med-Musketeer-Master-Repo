"use client";

import Link from "next/link";
import { useState } from "react";
import type { PatientExport } from "@/api/types";
import { ApiError } from "@/api/errors";
import { useData } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmButton } from "@/components/ui/confirm-button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select, TextInput } from "@/components/ui/form";
import { SectionTitle } from "@/components/ui/metric";
import { Notice } from "@/components/ui/notice";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Status, statusTone } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatAgo, formatDateTime } from "@/lib/date-time";
import { labelize } from "@/lib/labels";
import { loadPeople, NAMES_UNAVAILABLE, peopleById, personName } from "@/lib/people";
import { useAction } from "@/lib/use-action";
import { useResource } from "@/lib/use-resource";
import { AUDIT_LIMIT } from "./org-audit-log";
import { OrgAuditTable } from "./org-audit-table";

/** The export as a file the admin can hand over; the API returns it once per export. */
export function exportFile(record: PatientExport): { name: string; url: string } {
  const day = record.created_at.slice(0, 10);
  const blob = new Blob([JSON.stringify(record, null, 2)], { type: "application/json" });
  return { name: `${String(record.patient.pseudonym)}-export-${day}.json`, url: URL.createObjectURL(blob) };
}

const plural = (n: number, noun: string) => `${n} ${noun}${n === 1 ? "" : "s"}`;

function ExportResult({ record, onClose }: { record: PatientExport; onClose: () => void }) {
  return (
    <Card className="space-y-3 p-4" role="region" aria-label="Export">
      <p className="text-sm">
        Exported {String(record.patient.pseudonym)} for <strong>{record.destination}</strong> at {formatDateTime(record.created_at)}: {plural(record.disorders.length, "disorder")},{" "}
        {plural(record.care_assignments.length, "care assignment")}, {plural(record.wearable_assignments.length, "wearable assignment")}.
        {!record.ecg_included && " ECG is not included in exports yet."} The export is in the audit log.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={() => {
            const file = exportFile(record);
            const link = Object.assign(document.createElement("a"), { href: file.url, download: file.name });
            link.click();
            setTimeout(() => URL.revokeObjectURL(file.url), 0);
          }}
        >
          Download JSON
        </Button>
        <Button type="button" variant="secondary" onClick={onClose}>
          Close
        </Button>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-[var(--color-text-muted)]">Show the exported record</summary>
        <pre className="mt-2 max-h-80 overflow-auto rounded-[var(--radius-sm)] bg-[var(--color-surface-subtle)] p-3 text-xs">{JSON.stringify(record, null, 2)}</pre>
      </details>
    </Card>
  );
}

export function PatientDetail({ patientId }: { patientId: string }) {
  const { data } = useData();
  const action = useAction();
  const [doctorId, setDoctorId] = useState("");
  const [wearableId, setWearableId] = useState("");
  const [disorder, setDisorder] = useState("");
  const [destination, setDestination] = useState("");
  // Held above <Loaded>, like an invite code: a reload must not lose a finished export.
  const [exported, setExported] = useState<PatientExport | null>(null);

  const resource = useResource(async () => {
    const [patients, disorders, devices, accounts, audit, { people, named }] = await Promise.all([
      data.patients(),
      data.disorders(patientId),
      data.devices(),
      data.org.accounts(),
      data.org.audit(AUDIT_LIMIT),
      loadPeople(data.directory),
    ]);
    const patient = patients.find((p) => p.patient_id === patientId);
    if (!patient) throw new ApiError(404, "patient not found");
    return { patient, patients, disorders, devices, accounts, audit, people, named };
  }, [patientId]);

  async function change<T>(name: string, task: () => Promise<T>, success: string) {
    const done = await action.run(name, task, success);
    if (done !== undefined) resource.reload();
    return done;
  }
  const busy = action.busy !== null;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <Loaded resource={resource} label="Loading the patient">
        {({ patient, patients, disorders, devices, accounts, audit, people, named }) => {
          const byId = peopleById(people);
          const name = patient.user_id ? personName(byId.get(patient.user_id)) : null;
          const doctorName = (id: string) => personName(byId.get(id)) ?? `Doctor ${id.slice(0, 8)}`;
          const disabled = patient.account_status !== "active";
          const doctors = accounts.filter((a) => a.role === "doctor" && a.status === "active" && a.user_id !== patient.doctor_id);
          const wearable = devices.find((d) => d.device_id === patient.wearable_id);
          const issuable = devices.filter((d) => d.type === "wearable" && d.status === "active" && d.patient_id === null);
          const history = audit.filter((e) => e.target_id === patientId || (patient.user_id !== null && e.target_id === patient.user_id));

          return (
            <section className="space-y-5">
              <PageIntro
                title={patient.pseudonym}
                description={`${name ?? "Name not available"} · patient since ${formatDateTime(patient.created_at)}`}
                actions={<Status label={`Account ${labelize(patient.account_status ?? "none").toLowerCase()}`} tone={statusTone(patient.account_status)} />}
              />
              <p className="text-sm">
                <Link href="/org/patients" className="text-[var(--color-info)] underline">All patients</Link>
              </p>
              {!named && <p className="text-xs text-[var(--color-text-muted)]">{NAMES_UNAVAILABLE}</p>}
              {disabled && (
                <p className="border-l-2 border-[var(--color-warning)] px-3 py-2 text-sm">
                  This patient&apos;s account is disabled: no doctor can be assigned and no wearable issued. Their records stay and can be exported.
                </p>
              )}
              <Notice notice={action.notice} />

              <div className="grid gap-4 lg:grid-cols-2">
                <Card className="space-y-3 p-4">
                  <h3 className="font-semibold">Doctor</h3>
                  <p className="text-sm">
                    {patient.doctor_id ? (
                      <>Cared for by <strong>{doctorName(patient.doctor_id)}</strong>, who sees their ECG and alerts.</>
                    ) : (
                      <span className="text-[var(--color-warning)]">No doctor: no one sees this patient&apos;s alerts.</span>
                    )}
                  </p>
                  {!disabled && (
                    <form
                      className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end"
                      onSubmit={async (event) => {
                        event.preventDefault();
                        const chosen = doctorName(doctorId);
                        if (doctorId && (await change("assign", () => data.org.assignDoctor(patientId, doctorId), `${chosen} is now ${patient.pseudonym}'s doctor.`))) setDoctorId("");
                      }}
                    >
                      <Field label={patient.doctor_id ? "Change doctor" : "Assign a doctor"}>
                        <Select value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
                          <option value="">Choose a doctor</option>
                          {doctors.map((d) => (
                            <option key={d.user_id} value={d.user_id}>{doctorName(d.user_id)}</option>
                          ))}
                        </Select>
                      </Field>
                      <Button type="submit" disabled={busy || !doctorId}>{patient.doctor_id ? "Change" : "Assign"}</Button>
                    </form>
                  )}
                  {!disabled && patient.doctor_id && <p className="text-xs text-[var(--color-text-muted)]">A patient has one doctor at a time: changing it ends the current assignment.</p>}
                </Card>

                <Card className="space-y-3 p-4">
                  <h3 className="font-semibold">Wearable</h3>
                  {patient.wearable_id ? (
                    <>
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                        <dt className="text-[var(--color-text-muted)]">Device</dt>
                        <dd><RecordId id={patient.wearable_id} /></dd>
                        <dt className="text-[var(--color-text-muted)]">Status</dt>
                        <dd>{wearable ? <Status label={labelize(wearable.status)} tone={statusTone(wearable.status)} /> : "—"}</dd>
                        <dt className="text-[var(--color-text-muted)]">Path</dt>
                        <dd>{wearable ? labelize(wearable.current_mode) : "—"}{wearable?.current_gateway_id && <> via <RecordId id={wearable.current_gateway_id} /></>}</dd>
                        <dt className="text-[var(--color-text-muted)]">Last heard from</dt>
                        <dd>{formatAgo(wearable?.last_seen ?? null)}</dd>
                      </dl>
                      <ConfirmButton
                        label="Return wearable"
                        variant="danger"
                        title={`Return ${patient.pseudonym}'s wearable?`}
                        consequences={[
                          "Monitoring ends: data the wearable sends afterwards is not attributed to this patient.",
                          "The wearable becomes free to issue to another patient.",
                        ]}
                        disabled={busy}
                        onConfirm={() => void change("return", () => data.org.returnWearable(patientId), "Wearable returned.")}
                      />
                    </>
                  ) : disabled ? (
                    <p className="text-sm text-[var(--color-text-muted)]">No wearable issued.</p>
                  ) : (
                    <form
                      className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end"
                      onSubmit={async (event) => {
                        event.preventDefault();
                        if (wearableId && (await change("issue", () => data.org.issueWearable(patientId, wearableId), "Wearable issued: its data is now this patient's."))) setWearableId("");
                      }}
                    >
                      <Field label="Issue a wearable" hint="Active wearables granted to your organisation and not issued to anyone.">
                        <Select value={wearableId} onChange={(e) => setWearableId(e.target.value)}>
                          <option value="">{issuable.length ? "Choose a wearable" : "No wearable free to issue"}</option>
                          {issuable.map((d) => (
                            <option key={d.device_id} value={d.device_id}>Wearable {d.device_id.slice(0, 8)}</option>
                          ))}
                        </Select>
                      </Field>
                      <Button type="submit" className="sm:mb-5" disabled={busy || !wearableId}>Issue</Button>
                    </form>
                  )}
                </Card>
              </div>

              <SectionTitle>Disorders</SectionTitle>
              {disorders.length ? (
                <Table label="Disorders" minWidth={520}>
                  <THead columns={["Disorder", "Recorded", "By"]} />
                  <tbody>
                    {disorders.map((d) => (
                      <Tr key={d.disorder}>
                        <Td className="font-medium">{d.disorder}</Td>
                        <Td className="metric-number whitespace-nowrap">{formatDateTime(d.recorded_at)}</Td>
                        <Td>{personName(byId.get(d.recorded_by)) ?? <RecordId id={d.recorded_by} />}</Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              ) : (
                <EmptyState title="No disorders recorded" description="Known conditions help the patient's doctor read their alerts." />
              )}
              <Card className="p-4">
                <form
                  className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end"
                  onSubmit={async (event) => {
                    event.preventDefault();
                    const value = disorder.trim();
                    if (value && (await change("disorder", () => data.org.recordDisorder(patientId, value), `Recorded "${value}".`))) setDisorder("");
                  }}
                >
                  <Field label="Record a disorder">
                    <TextInput value={disorder} onChange={(e) => setDisorder(e.target.value)} maxLength={200} placeholder="Such as Paroxysmal atrial fibrillation" />
                  </Field>
                  <Button type="submit" disabled={busy || !disorder.trim()}>Record</Button>
                </form>
              </Card>

              <SectionTitle>Export</SectionTitle>
              {exported ? (
                <ExportResult record={exported} onClose={() => setExported(null)} />
              ) : (
                <Card className="space-y-2 p-4">
                  <form
                    className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end"
                    onSubmit={async (event) => {
                      event.preventDefault();
                      const value = destination.trim();
                      const record = value && (await change("export", () => data.org.exportPatient(patientId, value), "Export ready."));
                      if (record) {
                        setExported(record);
                        setDestination("");
                      }
                    }}
                  >
                    <Field label="Destination" hint="Who receives it, such as a referral hospital. Recorded with the export.">
                      <TextInput value={destination} onChange={(e) => setDestination(e.target.value)} maxLength={500} />
                    </Field>
                    <Button type="submit" className="sm:mb-5" disabled={busy || !destination.trim()}>Export</Button>
                  </form>
                  <p className="text-xs text-[var(--color-text-muted)]">The export holds the pseudonym, disorders and care and wearable history. It does not include the name, e-mail or ECG.</p>
                </Card>
              )}

              <SectionTitle>History</SectionTitle>
              <OrgAuditTable events={history} patients={patients} people={people} empty="Changes to this patient are logged here." />
              {audit.length >= AUDIT_LIMIT && <p className="text-xs text-[var(--color-text-muted)]">Searched the newest {AUDIT_LIMIT} changes in your organisation only.</p>}
            </section>
          );
        }}
      </Loaded>
    </div>
  );
}
