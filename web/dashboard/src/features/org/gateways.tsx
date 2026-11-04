"use client";

import Link from "next/link";
import type { Connectivity, OrgGateway } from "@/api/types";
import { useData } from "@/auth/session";
import { EmptyState } from "@/components/ui/empty-state";
import { Metric } from "@/components/ui/metric";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Status, statusTone, type StatusTone } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatAgo, formatDateTime, formatDuration } from "@/lib/date-time";
import { labelize } from "@/lib/labels";
import { useResource } from "@/lib/use-resource";
import { usePolling } from "../care/use-polling";

/** How often gateway screens re-read the connectivity log. */
export const GATEWAY_POLL_MS = 15_000;

/** A gateway's connection to the cloud, as the connectivity log has it (D17). */
export function connection(c: Connectivity, now = Date.now()): { label: string; tone: StatusTone; detail: string } {
  if (c.state === "unknown" || !c.since) return { label: "Not reported", tone: "offline", detail: "No connection logged yet" };
  return c.state === "online"
    ? { label: "Online", tone: "healthy", detail: `Up ${formatDuration(c.since, now)}` }
    : { label: "Offline", tone: "critical", detail: `Down ${formatDuration(c.since, now)}` };
}

export function ConnectionStatus({ connectivity }: { connectivity: Connectivity }) {
  const c = connection(connectivity);
  return (
    <>
      <Status label={c.label} tone={c.tone} />
      <span className="block text-xs text-[var(--color-text-muted)]" title={connectivity.since ? formatDateTime(connectivity.since) : undefined}>{c.detail}</span>
    </>
  );
}

export function OrgGateways() {
  const { data } = useData();
  const resource = useResource(() => data.gateways.list(), []);
  usePolling(resource.reload, GATEWAY_POLL_MS);

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro
        title="Gateways"
        description="The fixed gateways granted to your organisation: whether each is connected to the cloud and for how long, the wearables on it, and when alerts came through it. What an alert said is for the patient's doctor."
      />
      <Loaded resource={resource} label="Loading gateways">
        {(gateways: OrgGateway[]) => gateways.length ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric label="Gateways" value={gateways.length} detail={`${gateways.filter((g) => g.status === "active").length} active`} />
              <Metric label="Online" value={`${gateways.filter((g) => g.connectivity.state === "online").length} / ${gateways.length}`} detail={`${gateways.filter((g) => g.connectivity.state === "offline").length} offline`} />
              <Metric label="Wearables connected" value={gateways.reduce((n, g) => n + g.wearables_connected, 0)} detail="Your wearables on a gateway now" />
              <Metric label="Alerts, last 24 h" value={gateways.reduce((n, g) => n + g.alerts_24h, 0)} detail="Through your gateways" />
            </div>
            <Table label="Gateways" minWidth={860}>
              <THead columns={["Gateway", "Status", "Connection", "Wearables connected", "Alerts (24 h)", "Last heard from"]} />
              <tbody>
                {gateways.map((g) => (
                  <Tr key={g.device_id}>
                    <Td>
                      <Link href={`/org/gateways/${g.device_id}`} className="text-[var(--color-info)] underline-offset-2 hover:underline"><RecordId id={g.device_id} /></Link>
                    </Td>
                    <Td><Status label={labelize(g.status)} tone={statusTone(g.status)} /></Td>
                    <Td><ConnectionStatus connectivity={g.connectivity} /></Td>
                    <Td>
                      <span className="metric-number">{g.wearables_connected}</span>
                      {g.other_wearables_connected > 0 && <span className="block text-xs text-[var(--color-text-muted)]">+{g.other_wearables_connected} of other organisations</span>}
                    </Td>
                    <Td>
                      <span className="metric-number">{g.alerts_24h}</span>
                      <span className="block text-xs text-[var(--color-text-muted)]">{g.last_alert_at ? `Last ${formatAgo(g.last_alert_at)}` : "None yet"}</span>
                    </Td>
                    <Td title={g.last_seen ? formatDateTime(g.last_seen) : undefined}>{formatAgo(g.last_seen)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
            <p className="text-xs text-[var(--color-text-muted)]">
              &quot;Connection&quot; is the gateway&apos;s session with the cloud, logged when it connects or drops. While a gateway is offline it keeps monitoring its wearables locally; its wearables are not counted as connected until it is back.
            </p>
          </>
        ) : (
          <EmptyState title="No gateways" description="The system administrator has not granted any fixed gateway to your organisation yet." />
        )}
      </Loaded>
    </section>
  );
}
