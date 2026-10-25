"use client";

import Link from "next/link";
import { useState } from "react";
import type { SecurityEvent } from "@/api/types";
import { useData } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select, TextInput } from "@/components/ui/form";
import { SectionTitle } from "@/components/ui/metric";
import { Notice } from "@/components/ui/notice";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { Unavailable } from "@/components/ui/unavailable";
import { isAvailable } from "@/config/capabilities";
import { formatDateTime } from "@/lib/date-time";
import { deviceType, labelize } from "@/lib/labels";
import { useAction } from "@/lib/use-action";
import { useResource } from "@/lib/use-resource";
import type { AttackTest } from "@/services/contracts";

/** Attack types run from the testbed machine (stack.md: SYN flood, port scan, ARP spoofing) or at
 * the application layer (MQTT flood, replay). */
const ATTACK_TYPES = ["syn_flood", "dos_flood", "port_scan", "mqtt_flood", "replay", "arp_spoof"];

/** The IDS/IPS events about the target inside the test's window: the ground truth for detection
 * latency and false negatives (stack.md, "Attack-testing"). */
function windowEvents(test: AttackTest, events: SecurityEvent[]) {
  const start = Date.parse(test.started_at);
  const end = test.ended_at ? Date.parse(test.ended_at) : Number.POSITIVE_INFINITY;
  return events
    .filter((e) => e.device_id === test.target_device_id && e.outcome !== "no_threat" && Date.parse(e.ts) >= start && Date.parse(e.ts) <= end)
    .sort((a, b) => a.ts.localeCompare(b.ts));
}

function AttackTestsScreen() {
  const { data } = useData();
  const action = useAction();
  const [form, setForm] = useState({ target: "", type: ATTACK_TYPES[0], rate: "500" });
  const resource = useResource(async () => {
    const [tests, devices, events] = await Promise.all([data.attackTests.list(), data.registry.devices(), data.registry.securityEvents(1000)]);
    return { tests, devices, events };
  }, []);

  async function change<T>(name: string, task: () => Promise<T>, success: string) {
    const done = await action.run(name, task, success);
    if (done !== undefined && resource.status === "ready") resource.reload();
    return done;
  }

  return (
    <Loaded resource={resource} label="Loading attack tests">
      {({ tests, devices, events }) => {
        const targets = devices.filter((d) => d.is_testbed && d.status === "active");
        const running = tests.filter((t) => t.ended_at === null);
        return (
          <>
            <Card className="space-y-3 p-4">
              <h3 className="font-semibold">Start an attack test</h3>
              <form
                className="grid gap-3 md:grid-cols-[1.4fr_1fr_10rem_auto] md:items-start"
                onSubmit={async (event) => {
                  event.preventDefault();
                  await change(
                    "start",
                    () => data.attackTests.start({ attack_type: form.type, target_device_id: form.target, params: { rate_pps: Number(form.rate) } }),
                    "Attack test started. Stop it when the run is over; its window is compared with the IDS events.",
                  );
                }}
              >
                <Field label="Target" hint="Testbed devices only; production devices are refused.">
                  <Select value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })} required>
                    <option value="">Choose a testbed device</option>
                    {targets.map((d) => (
                      <option key={d.device_id} value={d.device_id}>{deviceType(d.type)} {d.device_id.split("-")[0]}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="Attack">
                  <Select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                    {ATTACK_TYPES.map((t) => <option key={t} value={t}>{labelize(t)}</option>)}
                  </Select>
                </Field>
                <Field label="Rate (packets/s)">
                  <TextInput type="number" min={1} value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} />
                </Field>
                <Button type="submit" variant="danger" className="md:mt-6" disabled={action.busy !== null || !form.target}>Start</Button>
              </form>
              <Notice notice={action.notice} />
            </Card>

            <SectionTitle>Running</SectionTitle>
            {running.length ? (
              <Table label="Running attack tests" minWidth={640}>
                <THead columns={["Attack", "Target", "Started", ""]} />
                <tbody>
                  {running.map((t) => (
                    <Tr key={t.test_id}>
                      <Td className="font-medium">{labelize(t.attack_type)}</Td>
                      <Td><Link href={`/system/devices/${t.target_device_id}`} className="text-[var(--color-info)]"><RecordId id={t.target_device_id} /></Link></Td>
                      <Td className="metric-number">{formatDateTime(t.started_at)}</Td>
                      <Td><Button type="button" variant="secondary" disabled={action.busy !== null} onClick={() => void change("stop", () => data.attackTests.stop(t.test_id), "Attack test stopped.")}>Stop</Button></Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="No attack test running" description="Start one above against a testbed device." />
            )}

            <SectionTitle>Results</SectionTitle>
            {tests.length ? (
              <Table label="Attack test results" minWidth={860}>
                <THead columns={["Attack", "Target", "Window", "Events in window", "First detection after"]} />
                <tbody>
                  {tests.map((t) => {
                    const inWindow = windowEvents(t, events);
                    const latency = inWindow.length ? Math.round((Date.parse(inWindow[0].ts) - Date.parse(t.started_at)) / 1000) : null;
                    return (
                      <Tr key={t.test_id}>
                        <Td className="font-medium">{labelize(t.attack_type)}</Td>
                        <Td><RecordId id={t.target_device_id} /></Td>
                        <Td className="metric-number text-xs">{formatDateTime(t.started_at)} – {t.ended_at ? formatDateTime(t.ended_at) : "running"}</Td>
                        <Td>{inWindow.length ? `${inWindow.length} (${[...new Set(inWindow.map((e) => labelize(e.predicted_class)))].join(", ")})` : <span className="text-[var(--color-critical)]">None: a missed detection</span>}</Td>
                        <Td className="metric-number">{latency === null ? "—" : `${latency} s`}</Td>
                      </Tr>
                    );
                  })}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="No attack tests yet" description="Results compare each test's window with what the gateway's IDS/IPS reported." />
            )}
          </>
        );
      }}
    </Loaded>
  );
}

export function AttackTests() {
  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Attack Tests" description="Controlled attacks against testbed devices. Each test's window is the ground truth for the IDS/IPS detection metrics." />
      {isAvailable("attackTests") ? (
        <AttackTestsScreen />
      ) : (
        <Unavailable feature="Attack testing" reason="The cloud does not serve attack tests yet; they arrive with the IDS/IPS integration (Iteration 5). Security events already show what the gateways report." />
      )}
    </section>
  );
}
