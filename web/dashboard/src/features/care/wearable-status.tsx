import type { OrgDevice } from "@/api/types";
import { Card } from "@/components/ui/card";
import { RecordId } from "@/components/ui/record-id";
import { Status, statusTone } from "@/components/ui/status";
import { formatAgo, formatDateTime } from "@/lib/date-time";
import { labelize } from "@/lib/labels";

/** What the cloud knows of a wearable: registry status, the path it last used, and when it last
 * heard from it. No online/offline verdict: a quiet wearable may have switched path, or its gateway
 * may be unreachable (stack.md, liveness), and how the paths reconcile is still open. */
export function WearableStatus({ wearable }: { wearable: OrgDevice | null }) {
  if (!wearable) {
    return (
      <Card className="p-4">
        <h3 className="font-semibold">Wearable</h3>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">No wearable issued: no ECG is being monitored. The organisation administrator issues one.</p>
      </Card>
    );
  }
  const path = wearable.current_mode === "fixed" ? "Fixed path, through a gateway" : wearable.current_mode === "mobile" ? "Mobile path, through the phone" : "Path not known yet";
  return (
    <Card className="space-y-2 p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-semibold">Wearable <RecordId id={wearable.device_id} /></h3>
        <Status label={labelize(wearable.status)} tone={statusTone(wearable.status)} />
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-[var(--color-text-muted)]">Path</dt>
        <dd>{path}{wearable.current_gateway_id && <> (<RecordId id={wearable.current_gateway_id} />)</>}</dd>
        <dt className="text-[var(--color-text-muted)]">Last heard from</dt>
        <dd title={wearable.last_seen ? formatDateTime(wearable.last_seen) : undefined}>{formatAgo(wearable.last_seen)}</dd>
      </dl>
      {wearable.status !== "active" && <p className="text-sm text-[var(--color-warning)]">The wearable is {wearable.status}: the broker refuses it, so no new ECG arrives.</p>}
    </Card>
  );
}
