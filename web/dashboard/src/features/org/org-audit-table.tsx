import Link from "next/link";
import type { AuditEvent, PatientSummary, Person } from "@/api/types";
import { useData } from "@/auth/session";
import { EmptyState } from "@/components/ui/empty-state";
import { RecordId } from "@/components/ui/record-id";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatDateTime } from "@/lib/date-time";
import { labelize, shortId } from "@/lib/labels";
import { peopleById, personName } from "@/lib/people";

/** Actions whose target is a patient (organisation.py audits them with target_id = patient_id). */
const PATIENT_ACTIONS = new Set(["doctor.assigned", "wearable.issued", "wearable.returned", "disorder.recorded", "patient.exported"]);

export interface AuditContext {
  people: Person[];
  patients: PatientSummary[];
}

export function OrgAuditTable({ events, people, patients, empty }: AuditContext & { events: AuditEvent[]; empty?: string }) {
  const { session } = useData();
  const byId = peopleById(people);
  const patientById = new Map(patients.map((p) => [p.patient_id, p]));
  const patientByUser = new Map(patients.filter((p) => p.user_id).map((p) => [p.user_id!, p]));
  const name = (userId: string) => personName(byId.get(userId));

  function target(event: AuditEvent): React.ReactNode {
    const id = event.target_id;
    if (!id) return "—";
    const patient = PATIENT_ACTIONS.has(event.action) ? patientById.get(id) : patientByUser.get(id);
    if (patient) {
      return <Link href={`/org/patients/${patient.patient_id}`} className="text-[var(--color-info)]">{patient.pseudonym}</Link>;
    }
    if (event.action.startsWith("account.")) return name(id) ?? <RecordId id={id} />;
    if (event.action.startsWith("organisation.")) return "This organisation";
    return <RecordId id={id} />;
  }

  function actor(event: AuditEvent): React.ReactNode {
    if (event.actor_id === session.userId) return "You";
    // The system administrator is outside the organisation, so the directory does not name them.
    return name(event.actor_id) ?? (event.scope === "registry" ? "System administrator" : <RecordId id={event.actor_id} />);
  }

  function details(event: AuditEvent): string {
    return Object.entries(event.details ?? {})
      .filter(([, value]) => value !== null && value !== undefined)
      .map(([key, value]) => {
        const text = String(value);
        const shown = key.endsWith("doctor_id") ? (name(text) ?? shortId(text)) : key.endsWith("_id") ? shortId(text) : key === "role" ? labelize(text) : text;
        return `${labelize(key.replace(/_id$/, ""))}: ${shown}`;
      })
      .join(" · ");
  }

  if (!events.length) return <EmptyState title="No changes yet" description={empty ?? "Changes in your organisation are logged here with who made them."} />;
  return (
    <Table label="Audit log" minWidth={820}>
      <THead columns={["Time", "Action", "Target", "By", "Details"]} />
      <tbody>
        {events.map((event) => (
          <Tr key={event.event_id}>
            <Td className="metric-number whitespace-nowrap">{formatDateTime(event.at)}</Td>
            <Td className="font-medium">{labelize(event.action)}</Td>
            <Td>{target(event)}</Td>
            <Td>{actor(event)}</Td>
            <Td className="text-xs text-[var(--color-text-muted)]">{details(event) || "—"}</Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  );
}
