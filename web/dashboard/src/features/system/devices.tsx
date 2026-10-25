"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useData } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Checkbox, Field, Select, TextInput } from "@/components/ui/form";
import { Notice } from "@/components/ui/notice";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Status, statusTone } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatAgo } from "@/lib/date-time";
import { deviceType, labelize } from "@/lib/labels";
import { useAction } from "@/lib/use-action";
import { useResource } from "@/lib/use-resource";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function RegisterDevice({ onRegistered }: { onRegistered: (deviceId: string) => void }) {
  const { data } = useData();
  const { busy, notice, run } = useAction();
  const [deviceId, setDeviceId] = useState("");
  const [type, setType] = useState<"wearable" | "fixed_gateway">("wearable");
  const [testbed, setTestbed] = useState(true);
  const valid = UUID.test(deviceId.trim());

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const id = deviceId.trim().toLowerCase();
    if (await run("register", () => data.registry.registerDevice({ device_id: id, type, is_testbed: testbed }), "Device registered. Add its certificate's fingerprint on its page, then activate it.")) {
      setDeviceId("");
      onRegistered(id);
    }
  }

  return (
    <Card className="space-y-3 p-4">
      <h3 className="font-semibold">Register a device</h3>
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-[1.6fr_1fr_auto_auto] md:items-start">
        <Field label="Device id" hint="The UUID the device's certificate was issued for (mmca issue … --device-id).">
          <TextInput
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
            required
            spellCheck={false}
            placeholder="xxxxxxxx-xxxx-4xxx-xxxx-xxxxxxxxxxxx"
            aria-invalid={deviceId !== "" && !valid}
            className="font-mono"
          />
        </Field>
        <Field label="Type">
          <Select value={type} onChange={(e) => setType(e.target.value as "wearable" | "fixed_gateway")}>
            <option value="wearable">Wearable</option>
            <option value="fixed_gateway">Fixed gateway</option>
          </Select>
        </Field>
        <div className="md:mt-8">
          <Checkbox label="Testbed device" checked={testbed} onChange={(e) => setTestbed(e.target.checked)} />
        </div>
        <Button type="submit" className="md:mt-6" disabled={busy !== null || !valid}>
          {busy ? "Registering…" : "Register"}
        </Button>
      </form>
      {deviceId !== "" && !valid && <p className="text-xs text-[var(--color-critical)]">Enter a UUID such as 3f2b6c1e-8a4d-4f0e-9b7a-1c2d3e4f5a6b.</p>}
      <p className="text-xs text-[var(--color-text-muted)]">Only testbed devices can be targets of attack tests. A new device starts as pending.</p>
      <Notice notice={notice} />
    </Card>
  );
}

export function Devices() {
  const { data } = useData();
  const resource = useResource(() => data.registry.devices(), []);
  const [filter, setFilter] = useState({ query: "", type: "", status: "", testbed: "" });

  const devices = resource.status === "ready" ? resource.data : null;
  const filtered = useMemo(() => {
    if (!devices) return [];
    return devices.filter(
      (d) =>
        d.device_id.includes(filter.query.trim().toLowerCase()) &&
        (!filter.type || d.type === filter.type) &&
        (!filter.status || d.status === filter.status) &&
        (!filter.testbed || String(d.is_testbed) === filter.testbed),
    );
  }, [devices, filter]);

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Devices" description="Every wearable and fixed gateway known to the cloud. Status here decides whether the broker lets a device in." />
      <RegisterDevice onRegistered={() => resource.reload()} />
      <div className="grid gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Search by id">
          <TextInput value={filter.query} onChange={(e) => setFilter({ ...filter, query: e.target.value })} placeholder="Part of the UUID" className="font-mono" />
        </Field>
        <Field label="Type">
          <Select value={filter.type} onChange={(e) => setFilter({ ...filter, type: e.target.value })}>
            <option value="">All types</option>
            <option value="wearable">Wearable</option>
            <option value="fixed_gateway">Fixed gateway</option>
          </Select>
        </Field>
        <Field label="Status">
          <Select value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })}>
            <option value="">All statuses</option>
            {["pending", "active", "suspended", "revoked"].map((s) => (
              <option key={s} value={s}>{labelize(s)}</option>
            ))}
          </Select>
        </Field>
        <Field label="Testbed">
          <Select value={filter.testbed} onChange={(e) => setFilter({ ...filter, testbed: e.target.value })}>
            <option value="">Testbed and production</option>
            <option value="true">Testbed only</option>
            <option value="false">Production only</option>
          </Select>
        </Field>
      </div>
      <Loaded resource={resource} label="Loading devices">
        {() =>
          filtered.length ? (
            <Table label="Devices" minWidth={820}>
              <THead columns={["Device", "Type", "Status", "Testbed", "Mode", "Last seen"]} />
              <tbody>
                {filtered.map((d) => (
                  <Tr key={d.device_id}>
                    <Td>
                      <Link href={`/system/devices/${d.device_id}`} className="font-mono text-xs text-[var(--color-info)] underline-offset-2 hover:underline">
                        {d.device_id}
                      </Link>
                    </Td>
                    <Td>{deviceType(d.type)}</Td>
                    <Td><Status label={labelize(d.status)} tone={statusTone(d.status)} /></Td>
                    <Td>{d.is_testbed ? "Testbed" : "Production"}</Td>
                    <Td>{labelize(d.current_mode)}{d.current_gateway_id && <span className="block text-xs text-[var(--color-text-muted)]">via <RecordId id={d.current_gateway_id} /></span>}</Td>
                    <Td>{formatAgo(d.last_seen)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <EmptyState title="No devices match" description="Change the filters, or register a device above." />
          )
        }
      </Loaded>
    </section>
  );
}
