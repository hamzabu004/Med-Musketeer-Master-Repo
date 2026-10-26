"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { SecurityEvent } from "@/api/types";
import { useData } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Select } from "@/components/ui/form";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { formatDateTime } from "@/lib/date-time";
import { labelize } from "@/lib/labels";
import { useResource } from "@/lib/use-resource";
import { SecurityEventTable } from "./security-event-table";

function EventDetail({ event, onClose }: { event: SecurityEvent; onClose: () => void }) {
  const rows: [string, React.ReactNode][] = [
    ["Time", formatDateTime(event.ts)],
    ["Mode", event.mode === "ips" ? "IPS (prevention: may act)" : "IDS (detection only)"],
    ["Predicted class", labelize(event.predicted_class)],
    ["Outcome", labelize(event.outcome)],
    ["Action", event.action ? labelize(event.action) : "None"],
    ["Action result", event.action_result ? labelize(event.action_result) : "—"],
    ["Gateway", <Link key="g" href={`/system/devices/${event.gateway_id}`} className="font-mono text-xs text-[var(--color-info)]">{event.gateway_id}</Link>],
    ["Device", event.device_id ? <Link key="d" href={`/system/devices/${event.device_id}`} className="font-mono text-xs text-[var(--color-info)]">{event.device_id}</Link> : "Not attributed to a device"],
    ["Event id", <span key="e" className="font-mono text-xs">{event.event_id}</span>],
  ];
  return (
    <Card className="space-y-3 p-4" role="region" aria-label="Security event detail">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Event detail</h3>
        <Button type="button" variant="secondary" onClick={onClose}>Close</Button>
      </div>
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        {rows.map(([term, value]) => (
          <div key={term}>
            <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">{term}</dt>
            <dd className="mt-0.5 break-all">{value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

export function SecurityEvents() {
  const { data } = useData();
  const resource = useResource(() => data.registry.securityEvents(1000), []);
  const [filter, setFilter] = useState({ mode: "", outcome: "", predicted: "" });
  const [selected, setSelected] = useState<SecurityEvent | null>(null);

  const loaded = resource.status === "ready" ? resource.data : null;
  const events = useMemo(() => loaded ?? [], [loaded]);
  const options = (key: "outcome" | "predicted_class") => [...new Set(events.map((e) => e[key]))].sort();
  const filtered = useMemo(
    () => events.filter((e) => (!filter.mode || e.mode === filter.mode) && (!filter.outcome || e.outcome === filter.outcome) && (!filter.predicted || e.predicted_class === filter.predicted)),
    [events, filter],
  );

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Security Events" description="What the gateways' IDS/IPS reported, newest first. Read-only: the gateway decides and acts; the cloud records." />
      <div className="grid gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:grid-cols-3">
        <Field label="Mode">
          <Select value={filter.mode} onChange={(e) => setFilter({ ...filter, mode: e.target.value })}>
            <option value="">IDS and IPS</option>
            <option value="ids">IDS</option>
            <option value="ips">IPS</option>
          </Select>
        </Field>
        <Field label="Predicted class">
          <Select value={filter.predicted} onChange={(e) => setFilter({ ...filter, predicted: e.target.value })}>
            <option value="">All classes</option>
            {options("predicted_class").map((v) => <option key={v} value={v}>{labelize(v)}</option>)}
          </Select>
        </Field>
        <Field label="Outcome">
          <Select value={filter.outcome} onChange={(e) => setFilter({ ...filter, outcome: e.target.value })}>
            <option value="">All outcomes</option>
            {options("outcome").map((v) => <option key={v} value={v}>{labelize(v)}</option>)}
          </Select>
        </Field>
      </div>
      {selected && <EventDetail event={selected} onClose={() => setSelected(null)} />}
      <Loaded resource={resource} label="Loading security events">
        {() => <SecurityEventTable events={filtered} empty="No events match. The gateways report here as they detect." onSelect={setSelected} />}
      </Loaded>
    </section>
  );
}
