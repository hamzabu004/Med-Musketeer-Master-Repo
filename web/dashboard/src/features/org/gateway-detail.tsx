"use client";

import Link from "next/link";
import { useState } from "react";
import type { ConnectivityEvent } from "@/api/types";
import { useData } from "@/auth/session";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select } from "@/components/ui/form";
import { SectionTitle } from "@/components/ui/metric";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Status, statusTone } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatAgo, formatDateTime, formatDuration } from "@/lib/date-time";
import { labelize, shortId } from "@/lib/labels";
import { useResource } from "@/lib/use-resource";
import { usePolling } from "../care/use-polling";
import { ConnectionStatus, GATEWAY_POLL_MS } from "./gateways";

/** Rows the screens ask for; the API serves up to 1000. */
export const GATEWAY_LOG_LIMIT = 200;

/** What a connectivity row means: a gateway connects to the cloud, a wearable joins or leaves the gateway. */
export function eventLabel(event: Pick<ConnectivityEvent, "device_type" | "state">): string {
  if (event.device_type === "fixed_gateway") return event.state === "online" ? "Connected to the cloud" : "Disconnected from the cloud";
  return event.state === "online" ? "Wearable joined" : "Wearable left";
}

type LogFilter = "" | "fixed_gateway" | "wearable";

export function GatewayDetail({ gatewayId }: { gatewayId: string }) {
  const { data } = useData();
  const [filter, setFilter] = useState<LogFilter>("");
  const resource = useResource(async () => {
    const [gateway, events, alerts, patients] = await Promise.all([
      data.gateways.detail(gatewayId),
      data.gateways.connectivity(gatewayId, GATEWAY_LOG_LIMIT),
      data.gateways.alerts(gatewayId, GATEWAY_LOG_LIMIT),
      data.patients(),
    ]);
    return { gateway, events, alerts, patients };
  }, [gatewayId]);
  usePolling(resource.reload, GATEWAY_POLL_MS);

  return (
    <Loaded resource={resource} label="Loading the gateway">
      {({ gateway, events, alerts, patients }, { fetchedAt }) => {
        const pseudonym = new Map(patients.map((p) => [p.patient_id, p.pseudonym]));
        const patientLink = (patientId: string | null) =>
          patientId ? <Link href={`/org/patients/${patientId}`} className="text-[var(--color-info)]">{pseudonym.get(patientId) ?? <RecordId id={patientId} />}</Link> : <span className="text-[var(--color-text-muted)]">Not issued</span>;
        const shown = events.filter((e) => !filter || e.device_type === filter);
        const facts: [string, React.ReactNode][] = [
          ["Connection", <ConnectionStatus key="c" connectivity={gateway.connectivity} />],
          [gateway.connectivity.state === "offline" ? "Offline since" : "Online since", gateway.connectivity.since ? formatDateTime(gateway.connectivity.since) : "—"],
          ["Last heard from", gateway.last_seen ? `${formatAgo(gateway.last_seen)} (${formatDateTime(gateway.last_seen)})` : "Never"],
          ["Wearables connected", gateway.other_wearables_connected ? `${gateway.wearables_connected} (+${gateway.other_wearables_connected} of other organisations)` : gateway.wearables_connected],
          ["Alerts, last 24 h", gateway.alerts_24h],
          ["Last alert", gateway.last_alert_at ? formatDateTime(gateway.last_alert_at) : "None yet"],
        ];
        return (
          <section className="mx-auto max-w-6xl space-y-5">
            <PageIntro
              title={`Fixed gateway ${shortId(gateway.device_id)}`}
              description={gateway.device_id}
              actions={<Status label={labelize(gateway.status)} tone={statusTone(gateway.status)} />}
            />
            <p className="text-sm">
              <Link href="/org/gateways" className="text-[var(--color-info)] underline">All gateways</Link>
            </p>
            <Card className="p-4">
              <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
                {facts.map(([term, value]) => (
                  <div key={term}>
                    <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">{term}</dt>
                    <dd className="mt-0.5">{value}</dd>
                  </div>
                ))}
              </dl>
            </Card>

            <SectionTitle>Connected wearables</SectionTitle>
            {gateway.wearables.length ? (
              <Table label="Connected wearables" minWidth={640}>
                <THead columns={["Wearable", "Issued to", "Connected for", "Last heard from"]} />
                <tbody>
                  {gateway.wearables.map((w) => (
                    <Tr key={w.device_id}>
                      <Td><RecordId id={w.device_id} /></Td>
                      <Td>{patientLink(w.patient_id)}</Td>
                      <Td title={w.connected_since ? formatDateTime(w.connected_since) : undefined}>{w.connected_since ? formatDuration(w.connected_since) : "—"}</Td>
                      <Td title={w.last_seen ? formatDateTime(w.last_seen) : undefined}>{formatAgo(w.last_seen)}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState
                title="No wearable connected"
                description={gateway.connectivity.state === "offline" ? "The gateway is offline: which wearables are on it is unknown until it reconnects." : "None of your wearables is on this gateway's fixed path now."}
              />
            )}

            <SectionTitle>Alerts through this gateway</SectionTitle>
            {alerts.length ? (
              <Table label="Alerts through this gateway" minWidth={560}>
                <THead columns={["Time", "Wearable", "Patient"]} />
                <tbody>
                  {alerts.map((a, i) => (
                    <Tr key={`${a.at}-${a.device_id}-${i}`}>
                      <Td className="whitespace-nowrap">
                        <span className="metric-number">{formatDateTime(a.at)}</span>
                        <span className="block text-xs text-[var(--color-text-muted)]">{formatAgo(a.at)}</span>
                      </Td>
                      <Td><RecordId id={a.device_id} /></Td>
                      <Td>{patientLink(a.patient_id)}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="No alerts" description="No alert from your patients has come through this gateway." />
            )}
            <p className="text-xs text-[var(--color-text-muted)]">Times only: the classification and ECG of an alert are for the patient&apos;s doctor.</p>

            <SectionTitle
              actions={
                <Field label="Show">
                  <Select value={filter} onChange={(e) => setFilter(e.target.value as LogFilter)}>
                    <option value="">Everything</option>
                    <option value="fixed_gateway">Gateway connections</option>
                    <option value="wearable">Wearables joining and leaving</option>
                  </Select>
                </Field>
              }
            >
              Connectivity log
            </SectionTitle>
            {shown.length ? (
              <Table label="Connectivity log" minWidth={640}>
                <THead columns={["Time", "Event", "Device", "Reason"]} />
                <tbody>
                  {shown.map((e) => (
                    <Tr key={e.event_id}>
                      <Td className="whitespace-nowrap">
                        <span className="metric-number">{formatDateTime(e.at)}</span>
                        <span className="block text-xs text-[var(--color-text-muted)]">{formatAgo(e.at)}</span>
                      </Td>
                      <Td><Status label={eventLabel(e)} tone={e.state === "online" ? "healthy" : e.device_type === "fixed_gateway" ? "critical" : "offline"} /></Td>
                      <Td>{e.device_type === "fixed_gateway" ? "This gateway" : <RecordId id={e.device_id} />}</Td>
                      <Td>{e.reason ? labelize(e.reason) : "—"}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="Nothing logged" description={events.length ? "Change the filter." : "The gateway has not connected to the cloud since logging began."} />
            )}
            <p className="text-xs text-[var(--color-text-muted)]">
              The newest {GATEWAY_LOG_LIMIT} entries. A row is written when the state changes, so the time of the newest gateway row is when its current connection began. Loaded {formatDateTime(new Date(fetchedAt).toISOString())}.
            </p>
          </section>
        );
      }}
    </Loaded>
  );
}
