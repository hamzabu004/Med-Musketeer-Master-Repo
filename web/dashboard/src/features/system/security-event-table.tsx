import Link from "next/link";
import type { SecurityEvent } from "@/api/types";
import { EmptyState } from "@/components/ui/empty-state";
import { RecordId } from "@/components/ui/record-id";
import { Status, statusTone } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatDateTime } from "@/lib/date-time";
import { labelize } from "@/lib/labels";

export function SecurityEventTable({ events, empty, onSelect }: { events: SecurityEvent[]; empty: string; onSelect?: (event: SecurityEvent) => void }) {
  if (!events.length) return <EmptyState title="Nothing to show" description={empty} />;
  return (
    <Table label="Security events" minWidth={860}>
      <THead columns={["Time", "Mode", "Predicted class", "Outcome", "Action", "Gateway", "Device"]} />
      <tbody>
        {events.map((event) => (
          <Tr key={event.event_id}>
            <Td className="metric-number whitespace-nowrap">
              {onSelect ? (
                <button type="button" className="text-[var(--color-info)] underline-offset-2 hover:underline" onClick={() => onSelect(event)}>
                  {formatDateTime(event.ts)}
                </button>
              ) : (
                formatDateTime(event.ts)
              )}
            </Td>
            <Td className="uppercase">{event.mode}</Td>
            <Td>{labelize(event.predicted_class)}</Td>
            <Td><Status label={labelize(event.outcome)} tone={statusTone(event.outcome)} /></Td>
            <Td>{event.action ? `${labelize(event.action)} (${labelize(event.action_result)})` : "—"}</Td>
            <Td><Link href={`/system/devices/${event.gateway_id}`} className="text-[var(--color-info)]"><RecordId id={event.gateway_id} /></Link></Td>
            <Td>{event.device_id ? <Link href={`/system/devices/${event.device_id}`} className="text-[var(--color-info)]"><RecordId id={event.device_id} /></Link> : "—"}</Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  );
}
