"use client";

import { FormEvent, useState } from "react";
import { MonitoringStationCard } from "@/components/monitoring/monitoring-station-card";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageIntro } from "@/components/ui/page-intro";
import { displayEmail } from "@/lib/display-identifiers";
import { services } from "@/services";
import type { DoctorOverview } from "./use-doctor-overview";
import { DoctorPageError, DoctorPageSkeleton } from "./doctor-page-state";
import { useDoctorOverview } from "./use-doctor-overview";

export function DoctorSettings() {
  const { state, retry } = useDoctorOverview();
  if (state.status === "loading") return <DoctorPageSkeleton />;
  if (state.status === "error") return <DoctorPageError message={state.message} onRetry={retry} />;
  return <DoctorSettingsContent overview={state.data} />;
}

function DoctorSettingsContent({ overview }: { overview: DoctorOverview }) {
  const [notificationsEnabled, setNotificationsEnabled] = useState(overview.preferences.notificationsEnabled);
  const [heartRateMonitoringIntervalSeconds, setHeartRateMonitoringIntervalSeconds] = useState(
    overview.preferences.heartRateMonitoringIntervalSeconds,
  );
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const patientNames = new Map(overview.patients.map((patient) => [patient.id, patient.displayName]));

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    try {
      await services.settings.save(overview.session.organizationId, {
        ...overview.preferences,
        notificationsEnabled,
        heartRateMonitoringIntervalSeconds,
      });
      setMessage("Monitoring preferences saved in this browser.");
    } catch {
      setError("The preference could not be saved. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <PageIntro title="Doctor Settings" description="Clinician profile, notifications, and assigned monitoring context." />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="text-lg font-semibold">Clinician profile</h3>
          <dl className="mt-4 grid gap-4 text-sm">
            <Detail label="Name" value={overview.doctor.displayName} />
            <Detail label="Account email" value={displayEmail(overview.user.email)} />
            <Detail label="Registered patients" value={String(overview.patients.length)} />
            <Detail label="Assigned Monitoring Stations" value={String(overview.stations.length)} />
          </dl>
        </Card>
        <Card className="p-5">
          <h3 className="text-lg font-semibold">Monitoring preferences</h3>
          <form className="mt-4" onSubmit={save}>
            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                checked={notificationsEnabled}
                onChange={(event) => setNotificationsEnabled(event.target.checked)}
                className="mt-0.5 size-4 accent-[var(--color-accent)]"
              />
              <span>
                <span className="block font-medium">Enable notifications</span>
                <span className="mt-1 block text-[var(--color-text-muted)]">Browser-only preference; no notification is delivered.</span>
              </span>
            </label>
            <label className="mt-5 block text-sm font-medium">
              Heart Rate Monitoring Interval
              <select
                className="mt-1 h-9 w-full rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-3 text-sm"
                value={heartRateMonitoringIntervalSeconds}
                onChange={(event) => setHeartRateMonitoringIntervalSeconds(Number(event.target.value) as typeof heartRateMonitoringIntervalSeconds)}
              >
                <option value={15}>15 seconds</option>
                <option value={30}>30 seconds</option>
                <option value={60}>1 minute</option>
                <option value={120}>2 minutes</option>
                <option value={300}>5 minutes</option>
              </select>
            </label>
            <Button type="submit" className="mt-5" disabled={saving}>{saving ? "Saving..." : "Save preferences"}</Button>
            {message && <p role="status" className="mt-3 text-sm text-[var(--color-healthy)]">{message}</p>}
            {error && <p role="alert" className="mt-3 text-sm text-[var(--color-critical)]">{error}</p>}
          </form>
        </Card>
      </div>

      <section aria-labelledby="settings-stations-heading" className="space-y-3">
        <h3 id="settings-stations-heading" className="text-lg font-semibold">Assigned Monitoring Stations</h3>
        {overview.stations.length ? (
          <div className="grid gap-4 lg:grid-cols-2">
            {overview.stations.map((station) => (
              <MonitoringStationCard
                key={station.id}
                station={station}
                associatedPatientNames={station.patientIds
                  .map((patientId) => patientNames.get(patientId))
                  .filter((name): name is string => Boolean(name))}
              />
            ))}
          </div>
        ) : (
          <EmptyState title="No assigned Monitoring Stations" description="No Monitoring Stations are assigned to this clinician." />
        )}
      </section>

      <Card className="p-5">
        <h3 className="text-lg font-semibold">Account</h3>
        <p className="mt-2 text-sm text-[var(--color-text-muted)]">This is a browser-only account, not a secure clinical authentication system.</p>
        <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
          <Detail label="Email" value={displayEmail(overview.user.email)} />
          <Detail label="Password" value="Provided by instructor" />
        </dl>
      </Card>
    </section>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-[var(--color-text-muted)]">{label}</dt><dd className="mt-1 font-medium metric-number">{value}</dd></div>;
}
