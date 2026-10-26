"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useData } from "@/auth/session";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select } from "@/components/ui/form";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Status, statusTone } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatAgo, formatDateTime } from "@/lib/date-time";
import { deviceType, labelize } from "@/lib/labels";
import { useResource } from "@/lib/use-resource";

export function OrgDevices() {
  const { data } = useData();
  const [filter, setFilter] = useState({ type: "", status: "" });
  const resource = useResource(async () => {
    const [devices, patients] = await Promise.all([data.devices(), data.patients()]);
    return { devices, patients };
  }, []);

  const loaded = resource.status === "ready" ? resource.data : null;
  const shown = useMemo(
    () => loaded?.devices.filter((d) => (!filter.type || d.type === filter.type) && (!filter.status || d.status === filter.status)) ?? [],
    [loaded, filter],
  );

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro
        title="Devices"
        description="Wearables and fixed gateways the system administrator has granted to your organisation. Issue a wearable from the patient's page; registering and suspending devices is the system administrator's job."
      />
      <div className="grid gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:grid-cols-2 lg:max-w-xl">
        <Field label="Type">
          <Select value={filter.type} onChange={(e) => setFilter({ ...filter, type: e.target.value })}>
            <option value="">All types</option>
            <option value="wearable">Wearables</option>
            <option value="fixed_gateway">Fixed gateways</option>
          </Select>
        </Field>
        <Field label="Status">
          <Select value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
            <option value="">All statuses</option>
            {["active", "suspended", "pending"].map((s) => (
              <option key={s} value={s}>{labelize(s)}</option>
            ))}
          </Select>
        </Field>
      </div>
      <Loaded resource={resource} label="Loading devices">
        {({ patients }) => {
          const pseudonym = new Map(patients.map((p) => [p.patient_id, p.pseudonym]));
          return shown.length ? (
            <>
              <Table label="Devices" minWidth={800}>
                <THead columns={["Device", "Type", "Status", "Path", "Last heard from", "Issued to"]} />
                <tbody>
                  {shown.map((d) => (
                    <Tr key={d.device_id}>
                      <Td><RecordId id={d.device_id} /></Td>
                      <Td>{deviceType(d.type)}</Td>
                      <Td><Status label={labelize(d.status)} tone={statusTone(d.status)} /></Td>
                      <Td>
                        {labelize(d.current_mode)}
                        {d.current_gateway_id && <span className="block text-xs text-[var(--color-text-muted)]">via <RecordId id={d.current_gateway_id} /></span>}
                      </Td>
                      <Td title={d.last_seen ? formatDateTime(d.last_seen) : undefined}>{formatAgo(d.last_seen)}</Td>
                      <Td>
                        {d.patient_id ? (
                          <Link href={`/org/patients/${d.patient_id}`} className="text-[var(--color-info)]">{pseudonym.get(d.patient_id) ?? <RecordId id={d.patient_id} />}</Link>
                        ) : d.type === "wearable" ? (
                          <span className="text-[var(--color-text-muted)]">Free</span>
                        ) : (
                          "—"
                        )}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
              <p className="text-xs text-[var(--color-text-muted)]">
                &quot;Last heard from&quot; is when the cloud last received anything from the device. A quiet wearable may have moved to the other path, or its gateway may be unreachable: it is not shown as offline.
              </p>
            </>
          ) : (
            <EmptyState title="No devices" description={loaded?.devices.length ? "Change the filters." : "The system administrator has not granted any device to your organisation yet."} />
          );
        }}
      </Loaded>
    </section>
  );
}
