"use client";

import { FormEvent, useState } from "react";
import { DeviceStatusCard } from "@/components/monitoring/device-status-card";
import { MonitoringStationCard } from "@/components/monitoring/monitoring-station-card";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageIntro } from "@/components/ui/page-intro";
import { displayEmail } from "@/lib/display-identifiers";
import { services } from "@/services";
import type { PatientOverview } from "./use-patient-overview";
import { PatientPageError, PatientPageSkeleton } from "./patient-page-state";
import { usePatientOverview } from "./use-patient-overview";

export function PatientSettings() {
  const { state, retry } = usePatientOverview();
  if (state.status === "loading") return <PatientPageSkeleton />;
  if (state.status === "error") return <PatientPageError message={state.message} onRetry={retry} />;

  return <PatientSettingsContent overview={state.data} />;
}

function PatientSettingsContent({ overview }: { overview: PatientOverview }) {
  const [notificationsEnabled, setNotificationsEnabled] = useState(overview.preferences.notificationsEnabled);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function save(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    try {
      await services.settings.save(overview.session.organizationId, {
        ...overview.preferences,
        notificationsEnabled,
      });
      setMessage("Notification preference saved in this browser.");
    } catch {
      setError("The preference could not be saved. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="mx-auto max-w-5xl space-y-5">
      <PageIntro title="Settings" description="Profile, notification, and assigned monitoring information." />

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="p-5">
          <h3 className="text-lg font-semibold">Profile</h3>
          <dl className="mt-4 grid gap-4 text-sm">
            <Detail label="Name" value={overview.patient.displayName} />
            <Detail label="Account email" value={displayEmail(overview.user.email)} />
            <Detail label="Account role" value="Patient" />
            <Detail label="Assigned clinician" value={overview.doctor?.displayName ?? "Not assigned"} />
          </dl>
        </Card>

        <Card className="p-5">
          <h3 className="text-lg font-semibold">Notifications</h3>
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
                <span className="mt-1 block text-[var(--color-text-muted)]">
                  This changes browser-only state. No notification is actually delivered.
                </span>
              </span>
            </label>
            <Button type="submit" className="mt-5" disabled={saving}>
              {saving ? "Saving…" : "Save preference"}
            </Button>
            {message && <p role="status" className="mt-3 text-sm text-[var(--color-healthy)]">{message}</p>}
            {error && <p role="alert" className="mt-3 text-sm text-[var(--color-critical)]">{error}</p>}
          </form>
        </Card>
      </div>

      <section aria-labelledby="assigned-equipment-heading" className="space-y-3">
        <h3 id="assigned-equipment-heading" className="text-lg font-semibold">Assigned monitoring equipment</h3>
        <div className="grid gap-4 lg:grid-cols-2">
          {overview.device ? (
            <DeviceStatusCard device={overview.device} />
          ) : (
            <EmptyState title="No wearable assigned" description="Wearable information is unavailable for this profile." />
          )}
          {overview.station ? (
            <MonitoringStationCard station={overview.station} />
          ) : (
            <EmptyState title="No Monitoring Station assigned" description="Monitoring Station information is unavailable for this profile." />
          )}
        </div>
      </section>

      <Card className="p-5">
        <h3 className="text-lg font-semibold">Account</h3>
        <p className="mt-2 text-sm text-[var(--color-text-muted)]">
          This account is for the MedMusketeer simulated environment only. It is not a secure authentication system.
        </p>
        <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
          <Detail label="Email" value={displayEmail(overview.user.email)} />
          <Detail label="Password" value="Provided by instructor" />
        </dl>
      </Card>
    </section>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[var(--color-text-muted)]">{label}</dt>
      <dd className="mt-1 font-medium">{value}</dd>
    </div>
  );
}
