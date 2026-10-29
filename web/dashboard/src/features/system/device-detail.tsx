"use client";

import Link from "next/link";
import { useState } from "react";
import type { Device, Organisation, RevocationStatus } from "@/api/types";
import { useData } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmButton } from "@/components/ui/confirm-button";
import { EmptyState } from "@/components/ui/empty-state";
import { Field, Select, TextInput } from "@/components/ui/form";
import { SectionTitle } from "@/components/ui/metric";
import { Notice } from "@/components/ui/notice";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { RecordId } from "@/components/ui/record-id";
import { Status, statusTone } from "@/components/ui/status";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatAgo, formatDateTime } from "@/lib/date-time";
import { deviceType, labelize, shortId } from "@/lib/labels";
import { useAction } from "@/lib/use-action";
import { useResource } from "@/lib/use-resource";
import { gatewayListState } from "./revocation-list";

/** A SHA-256 fingerprint as `mmca issue` prints it: 64 hex digits, colons allowed. */
export function normaliseFingerprint(value: string): string | null {
  const hex = value.replaceAll(":", "").replace(/\s/g, "").toUpperCase();
  return /^[0-9A-F]{64}$/.test(hex) ? hex : null;
}

function Facts({ device, revocation }: { device: Device; revocation: RevocationStatus }) {
  const listState = gatewayListState(device, revocation);
  const facts: [string, React.ReactNode][] = [
    ["Type", deviceType(device.type)],
    ["Testbed", device.is_testbed ? "Yes: attack tests may target it" : "No: production device"],
    ["Mode", labelize(device.current_mode)],
    ["Current gateway", device.current_gateway_id ? <Link href={`/system/devices/${device.current_gateway_id}`} className="text-[var(--color-info)]"><RecordId id={device.current_gateway_id} /></Link> : "—"],
    ["Last seen", device.last_seen ? `${formatAgo(device.last_seen)} (${formatDateTime(device.last_seen)})` : "Never"],
    ["Registered", formatDateTime(device.created_at)],
    ["Status since", formatDateTime(device.status_changed_at)],
  ];
  if (listState) {
    facts.push(["Revocation list", <>
      <Status label={listState.label} tone={listState.tone} />
      {listState.stale && <span className="mt-1 block text-xs text-[var(--color-text-muted)]">This gateway may still let in a wearable revoked since. It catches up when it next reaches the cloud.</span>}
    </>]);
  }
  return (
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
  );
}

export function DeviceDetail({ deviceId }: { deviceId: string }) {
  const { data } = useData();
  const action = useAction();
  const [fingerprint, setFingerprint] = useState("");
  const [grantTo, setGrantTo] = useState("");

  const resource = useResource(async () => {
    const [device, credentials, grants, organisations, revocation] = await Promise.all([
      data.registry.device(deviceId),
      data.registry.credentials(deviceId),
      data.registry.grants(deviceId),
      data.registry.organisations(),
      data.registry.revocation(),
    ]);
    return { device, credentials, grants, organisations, revocation };
  }, [deviceId]);

  async function change<T>(name: string, task: () => Promise<T>, success: string) {
    const done = await action.run(name, task, success);
    if (done !== undefined) resource.reload();
    return done;
  }

  const busy = action.busy !== null;
  const reference = normaliseFingerprint(fingerprint);

  return (
    <Loaded resource={resource} label="Loading the device">
      {({ device, credentials, grants, organisations, revocation }) => {
        const orgName = (id: string) => organisations.find((o: Organisation) => o.org_id === id)?.name ?? id;
        const openGrant = grants.find((g) => g.revoked_at === null);
        const activeCredentials = credentials.filter((c) => c.status === "active");
        const grantable = organisations.filter((o) => o.status === "active");
        const revoked = device.status === "revoked";
        const isGateway = device.type === "fixed_gateway";
        // What the broker does on each change (D16): gateways are disconnected at once; wearables are
        // refused by every gateway through the revocation list, which is matched by name, not certificate.
        const refusal = isGateway
          ? "It is disconnected from the cloud at once and refused when it reconnects."
          : "Every gateway refuses it within seconds through the revocation list, also while it cannot reach the cloud.";

        return (
          <section className="mx-auto max-w-6xl space-y-5">
            <PageIntro
              title={`${deviceType(device.type)} ${shortId(device.device_id)}`}
              description={device.device_id}
              actions={<Status label={labelize(device.status)} tone={statusTone(device.status)} />}
            />
            <p className="text-sm">
              <Link href="/system/devices" className="text-[var(--color-info)] underline">All devices</Link>
            </p>
            <Notice notice={action.notice} />
            <Facts device={device} revocation={revocation} />

            <SectionTitle>Lifecycle</SectionTitle>
            <Card className="flex flex-wrap items-center gap-2 p-4">
              {(device.status === "pending" || device.status === "suspended") && (
                <Button
                  type="button"
                  disabled={busy || activeCredentials.length === 0}
                  onClick={() => void change("activate", () => data.registry.activateDevice(deviceId), "Device activated: the broker now lets it connect.")}
                >
                  Activate
                </Button>
              )}
              {device.status === "active" && (
                <ConfirmButton
                  label="Suspend"
                  title="Suspend this device?"
                  consequences={[refusal, "Credentials, grant and assignment are kept; activating it again restores it."]}
                  disabled={busy}
                  onConfirm={() => void change("suspend", () => data.registry.suspendDevice(deviceId), "Device suspended.")}
                />
              )}
              {!revoked && (
                <ConfirmButton
                  label="Revoke"
                  variant="danger"
                  title="Revoke this device for good?"
                  consequences={[
                    `All its credentials are revoked. ${refusal}`,
                    "Its grant to an organisation ends, and if it is a wearable issued to a patient, it is returned.",
                    "This cannot be undone: a revoked device cannot be activated or granted again.",
                  ]}
                  disabled={busy}
                  onConfirm={() => void change("revoke", () => data.registry.revokeDevice(deviceId), "Device revoked.")}
                />
              )}
              {(device.status === "pending" || device.status === "suspended") && activeCredentials.length === 0 && (
                <p className="text-sm text-[var(--color-text-muted)]">Add an active credential before activating.</p>
              )}
              {revoked && <p className="text-sm text-[var(--color-text-muted)]">Revoked devices stay in the registry for the record.</p>}
            </Card>

            <SectionTitle>Credentials</SectionTitle>
            {credentials.length ? (
              <Table label="Credentials" minWidth={760}>
                <THead columns={["Method", "Reference", "Key", "Status", "Added", ""]} />
                <tbody>
                  {credentials.map((c) => (
                    <Tr key={c.credential_id}>
                      <Td>{labelize(c.auth_method)}</Td>
                      <Td className="max-w-[18rem] break-all font-mono text-xs">{c.credential_ref}</Td>
                      <Td>{c.key_type ?? "—"}</Td>
                      <Td><Status label={labelize(c.status)} tone={statusTone(c.status)} /></Td>
                      <Td className="metric-number">{formatDateTime(c.created_at)}</Td>
                      <Td>
                        {c.status === "active" && (
                          <ConfirmButton
                            label="Revoke"
                            title="Revoke this credential?"
                            consequences={isGateway
                              ? ["The cloud refuses this certificate from now on, and the gateway is disconnected at once.", "The device itself stays as it is; add a new credential for a replacement certificate."]
                              : ["The cloud refuses this certificate from now on.", "Gateways match wearables by name, not by certificate: to stop this wearable at the gateway too, suspend it until its new certificate is flashed.", "The device itself stays as it is; add a new credential for a replacement certificate."]}
                            disabled={busy}
                            onConfirm={() => void change("revoke-credential", () => data.registry.revokeCredential(c.credential_id), "Credential revoked.")}
                          />
                        )}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState title="No credentials" description="Add the certificate's fingerprint below; the device cannot be activated without one." />
            )}
            {!revoked && (
              <Card className="space-y-3 p-4">
                <h4 className="text-sm font-semibold">Add a certificate</h4>
                <form
                  className="grid gap-3 md:grid-cols-[1fr_auto] md:items-start"
                  onSubmit={async (event) => {
                    event.preventDefault();
                    if (!reference) return;
                    if (await change("add-credential", () => data.registry.addCredential(deviceId, { auth_method: "x509_mtls", credential_ref: reference }), "Credential added.")) {
                      setFingerprint("");
                    }
                  }}
                >
                  <Field label="SHA-256 fingerprint" hint="As mmca issue prints it; colons and lower case are fine. Never paste a private key.">
                    <TextInput
                      value={fingerprint}
                      onChange={(e) => setFingerprint(e.target.value)}
                      spellCheck={false}
                      className="font-mono"
                      aria-invalid={fingerprint !== "" && !reference}
                      placeholder="AB:CD:…"
                    />
                  </Field>
                  <Button type="submit" className="md:mt-6" disabled={busy || !reference}>Add</Button>
                </form>
                {fingerprint !== "" && !reference && <p className="text-xs text-[var(--color-critical)]">A SHA-256 fingerprint has 64 hex digits.</p>}
              </Card>
            )}

            <SectionTitle>Organisation grant</SectionTitle>
            <Card className="space-y-3 p-4">
              {openGrant ? (
                <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                  <p>
                    Granted to{" "}
                    <Link href={`/system/organisations/${openGrant.org_id}`} className="font-medium text-[var(--color-info)]">{orgName(openGrant.org_id)}</Link>{" "}
                    since {formatDateTime(openGrant.granted_at)}.
                  </p>
                  <ConfirmButton
                    label="End grant"
                    variant="danger"
                    title="End this grant?"
                    consequences={["The organisation can no longer issue or see this device.", "If it is a wearable issued to a patient, it is returned and its monitoring session ends."]}
                    disabled={busy}
                    onConfirm={() => void change("revoke-grant", () => data.registry.revokeGrant(openGrant.grant_id), "Grant ended.")}
                  />
                </div>
              ) : revoked ? (
                <p className="text-sm text-[var(--color-text-muted)]">A revoked device cannot be granted.</p>
              ) : (
                <form
                  className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-start"
                  onSubmit={async (event) => {
                    event.preventDefault();
                    if (grantTo && (await change("grant", () => data.registry.grantDevice(deviceId, grantTo), "Device granted."))) setGrantTo("");
                  }}
                >
                  <Field label="Grant to" hint="Only active organisations. A device belongs to one organisation at a time.">
                    <Select value={grantTo} onChange={(e) => setGrantTo(e.target.value)}>
                      <option value="">Choose an organisation</option>
                      {grantable.map((o) => (
                        <option key={o.org_id} value={o.org_id}>{o.name}</option>
                      ))}
                    </Select>
                  </Field>
                  <Button type="submit" className="sm:mt-6" disabled={busy || !grantTo}>Grant</Button>
                </form>
              )}
              {grants.length > 0 && (
                <details className="text-sm">
                  <summary className="cursor-pointer text-[var(--color-text-muted)]">Grant history ({grants.length})</summary>
                  <ul className="mt-2 space-y-1">
                    {grants.map((g) => (
                      <li key={g.grant_id}>
                        {orgName(g.org_id)}: {formatDateTime(g.granted_at)} – {g.revoked_at ? formatDateTime(g.revoked_at) : "now"}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </Card>
          </section>
        );
      }}
    </Loaded>
  );
}
