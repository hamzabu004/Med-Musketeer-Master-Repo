"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageIntro } from "@/components/ui/page-intro";
import { formatDateTime } from "@/lib/date-time";
import { services } from "@/services";
import type { Device } from "@/types";
import { AdminPageError, AdminPageSkeleton } from "./admin-page-state";
import { inputClass, LabeledStatus, tableWrapClass, tdClass, thClass } from "./admin-ui";
import { useAdminOverview } from "./use-admin-overview";

type PendingAssignment = {
  patientId: string;
  stationId: string;
};

export function AdminDevices() {
  const { state, refresh } = useAdminOverview();
  const [query, setQuery] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [pendingAssignments, setPendingAssignments] = useState<Record<string, PendingAssignment>>({});

  if (state.status === "loading") return <AdminPageSkeleton />;
  if (state.status === "error") return <AdminPageError message={state.message} onRetry={refresh} />;

  const data = state.data;
  const organizationId = data.session.organizationId;
  const rows = data.devices.filter((device) =>
    `${device.id} ${device.identity}`.toLowerCase().includes(query.toLowerCase()),
  );

  async function mutate(deviceId: string, task: () => Promise<unknown>, success: string) {
    setSaving(deviceId);
    setMessage("");
    try {
      await task();
      setMessage(success);
      setSaving(null);
      refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Device update failed.");
      setSaving(null);
    }
  }

  function stageAssignment(device: Device, field: keyof PendingAssignment, value: string) {
    setPendingAssignments((current) => {
      const original = {
        patientId: device.patientId ?? "",
        stationId: device.monitoringStationId ?? "",
      };
      const staged = {
        patientId: current[device.id]?.patientId ?? original.patientId,
        stationId: current[device.id]?.stationId ?? original.stationId,
        [field]: value,
      };

      if (staged.patientId === original.patientId && staged.stationId === original.stationId) {
        const next = { ...current };
        delete next[device.id];
        return next;
      }

      return { ...current, [device.id]: staged };
    });
  }

  function discardAssignment(deviceId: string) {
    setPendingAssignments((current) => {
      const next = { ...current };
      delete next[deviceId];
      return next;
    });
  }

  async function applyAssignment(device: Device) {
    const pending = pendingAssignments[device.id];
    if (!pending) return;

    const patientChanged = pending.patientId !== (device.patientId ?? "");
    const stationChanged = pending.stationId !== (device.monitoringStationId ?? "");
    const confirmed = window.confirm(
      "Apply this simulated assignment change? Patient and Monitoring Station relationships will be updated in browser state.",
    );
    if (!confirmed) return;

    await mutate(
      device.id,
      async () => {
        if (patientChanged) await services.devices.assignPatient(organizationId, device.id, pending.patientId || null);
        if (stationChanged) await services.devices.assignMonitoringStation(organizationId, device.id, pending.stationId || null);
        discardAssignment(device.id);
      },
      "Assignment change applied to browser state.",
    );
  }

  return (
    <section className="mx-auto max-w-[1500px] space-y-5">
      <PageIntro
        title="Device Management"
        description="Persisted browser-state controls for simulated ECG wearable identities and assignments."
        actions={
          <Link
            className="inline-flex h-9 items-center rounded-[var(--radius-sm)] border border-[var(--color-brand)] bg-[var(--color-brand)] px-3 text-sm font-medium text-[var(--color-on-brand)]"
            href="/admin/devices/register"
          >
            Register device
          </Link>
        }
      />
      <label className="block max-w-sm text-sm font-medium">
        Search devices
        <input
          className={inputClass}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Device ID or identity"
        />
      </label>
      {message && (
        <p role="status" className="border-l-2 border-[var(--color-accent)] bg-[var(--color-accent-soft)] px-3 py-2 text-sm">
          {message}
        </p>
      )}
      {!rows.length ? (
        <EmptyState title="No devices found" description="No registered wearable matches this search." />
      ) : (
        <div className={tableWrapClass}>
          <table className="w-full min-w-[1240px] text-sm">
            <thead className="bg-[var(--color-surface-subtle)] text-[var(--color-text-muted)]">
              <tr>
                {[
                  "Device / identity",
                  "Patient assignment",
                  "Monitoring Station",
                  "Connection",
                  "Last seen",
                  "Battery",
                  "Firmware",
                  "General health",
                  "Actions",
                ].map((heading) => (
                  <th className={thClass} key={heading}>
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((device) => {
                const patient = data.patients.find((item) => item.id === device.patientId);
                const station = data.stations.find((item) => item.id === device.monitoringStationId);
                const pending = pendingAssignments[device.id];
                const patientValue = pending?.patientId ?? device.patientId ?? "";
                const stationValue = pending?.stationId ?? device.monitoringStationId ?? "";

                return (
                  <tr key={device.id} className="border-t border-[var(--color-border)]">
                    <td className={tdClass}>
                      <b>{device.id}</b>
                      <br />
                      <span className="text-xs text-[var(--color-text-muted)]">{device.identity ?? "Not verified"}</span>
                    </td>
                    <td className={tdClass}>
                      <select
                        aria-label={`Patient assignment for ${device.id}`}
                        className="h-9 rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-2"
                        value={patientValue}
                        disabled={saving === device.id}
                        onChange={(event) => stageAssignment(device, "patientId", event.target.value)}
                      >
                        <option value="">Unassigned</option>
                        {data.patients.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.displayName}
                          </option>
                        ))}
                      </select>
                      {patient && <span className="mt-1 block text-xs text-[var(--color-text-muted)]">{patient.id}</span>}
                      {pending && <span className="mt-1 block text-xs font-medium text-[var(--color-warning)]">Pending review</span>}
                    </td>
                    <td className={tdClass}>
                      <select
                        aria-label={`Monitoring Station assignment for ${device.id}`}
                        className="h-9 max-w-56 rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-2"
                        value={stationValue}
                        disabled={saving === device.id}
                        onChange={(event) => stageAssignment(device, "stationId", event.target.value)}
                      >
                        <option value="">Unassigned</option>
                        {data.stations.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}
                          </option>
                        ))}
                      </select>
                      {station && <span className="mt-1 block text-xs text-[var(--color-text-muted)]">{station.id}</span>}
                      {pending && <span className="mt-1 block text-xs font-medium text-[var(--color-warning)]">Not yet applied</span>}
                    </td>
                    <td className={tdClass}>
                      <LabeledStatus value={device.status} />
                    </td>
                    <td className={`${tdClass} metric-number`}>{device.lastSeenAt ? formatDateTime(device.lastSeenAt) : "Never"}</td>
                    <td className={`${tdClass} metric-number`}>
                      {device.batteryPercent == null ? "—" : `${device.batteryPercent}%`}
                    </td>
                    <td className={tdClass}>{device.firmwareVersion ?? "—"}</td>
                    <td className={tdClass}>
                      {device.status === "online" && (device.batteryPercent ?? 100) > 25 ? (
                        <LabeledStatus value="healthy" />
                      ) : (
                        <LabeledStatus value={device.status === "disabled" ? "disabled" : "degraded"} />
                      )}
                    </td>
                    <td className={`${tdClass} space-y-2`}>
                      {pending && (
                        <>
                          <Button type="button" disabled={saving === device.id} onClick={() => void applyAssignment(device)}>
                            Apply assignment
                          </Button>
                          <br />
                          <Button type="button" variant="secondary" disabled={saving === device.id} onClick={() => discardAssignment(device.id)}>
                            Revert staged
                          </Button>
                          <br />
                        </>
                      )}
                      <Button
                        type="button"
                        variant={device.status === "disabled" ? "secondary" : "danger"}
                        disabled={saving === device.id}
                        onClick={() =>
                          void mutate(
                            device.id,
                            () => services.devices.setStatus(organizationId, device.id, device.status === "disabled" ? "online" : "disabled"),
                            device.status === "disabled" ? "Device activated." : "Device disabled.",
                          )
                        }
                      >
                        {device.status === "disabled" ? "Activate" : "Disable"}
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
