import Link from "next/link";
import type { AuditEvent, Organisation } from "@/api/types";
import { useData } from "@/auth/session";
import { EmptyState } from "@/components/ui/empty-state";
import { RecordId } from "@/components/ui/record-id";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatDateTime } from "@/lib/date-time";
import { formatAuditDetails } from "@/lib/audit";
import { labelize } from "@/lib/labels";

/** Where an audit row's target lives: devices for device, credential and grant actions,
 * organisations for organisation actions; account targets have no page for the system admin. */
function targetHref(event: AuditEvent): string | null {
  if (!event.target_id) return null;
  const [kind] = event.action.split(".");
  if (["device", "credential", "grant"].includes(kind)) return `/system/devices/${event.target_id}`;
  if (kind === "organisation") return `/system/organisations/${event.target_id}`;
  return null;
}

export function AuditTable({ events, organisations }: { events: AuditEvent[]; organisations: Organisation[] }) {
  const { session } = useData();
  const orgName = new Map(organisations.map((o) => [o.org_id, o.name]));
  if (!events.length) return <EmptyState title="No changes yet" description="Registry changes are logged here with who made them." />;
  return (
    <Table label="Audit log" minWidth={900}>
      <THead columns={["Time", "Action", "Target", "Organisation", "By", "Details"]} />
      <tbody>
        {events.map((event) => {
          const href = targetHref(event);
          return (
            <Tr key={event.event_id}>
              <Td className="metric-number whitespace-nowrap">{formatDateTime(event.at)}</Td>
              <Td className="font-medium">{labelize(event.action)}</Td>
              <Td>{href ? <Link href={href} className="text-[var(--color-info)]"><RecordId id={event.target_id} /></Link> : <RecordId id={event.target_id} />}</Td>
              <Td>{event.org_id ? <Link href={`/system/organisations/${event.org_id}`} className="text-[var(--color-info)]">{orgName.get(event.org_id) ?? <RecordId id={event.org_id} />}</Link> : "—"}</Td>
              <Td>{event.actor_id === session.userId ? "You" : <RecordId id={event.actor_id} />}</Td>
              <Td className="text-xs text-[var(--color-text-muted)]">{formatAuditDetails(event) || "—"}</Td>
            </Tr>
          );
        })}
      </tbody>
    </Table>
  );
}
