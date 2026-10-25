"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageIntro } from "@/components/ui/page-intro";
import { services } from "@/services";
import type { SystemPreferences } from "@/types";
import { AdminPageError, AdminPageSkeleton } from "./admin-page-state";
import { inputClass, LabeledStatus, SectionTitle } from "./admin-ui";
import { useAdminOverview } from "./use-admin-overview";

export function AdminSystemConfiguration() {
  const { state, refresh } = useAdminOverview();
  const [draft, setDraft] = useState<SystemPreferences | null>(null);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  if (state.status === "loading") return <AdminPageSkeleton />;
  if (state.status === "error") return <AdminPageError message={state.message} onRetry={refresh} />;
  const data = state.data;
  const organizationId = data.session.organizationId;
  const value = draft ?? data.preferences;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await services.settings.save(organizationId, value);
      setMessage("Simulated system preferences saved to browser state.");
      setDraft(null);
      setSaving(false);
      refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Configuration update failed.");
      setSaving(false);
    }
  }

  return <section className="mx-auto max-w-6xl space-y-5">
    <PageIntro title="Organization Configuration" description="Simulation controls for this organization's frontend state. Changes do not configure a real network, IDS, IPS, or clinical system." />
    {message && <p role="status" className="border-l-2 border-[var(--color-accent)] bg-[var(--color-accent-soft)] px-3 py-2 text-sm">{message}</p>}
    <form className="grid gap-4 lg:grid-cols-2" onSubmit={(event) => void save(event)}>
      <Card className="p-5"><SectionTitle description="These switches affect labels and preferences in local state only.">Simulated security policy</SectionTitle><div className="mt-4 space-y-4"><label className="flex items-center justify-between gap-4 text-sm"><span><b>IDS simulation</b><span className="block text-xs text-[var(--color-text-muted)]">Show intrusion-detection capability as enabled in browser state.</span></span><input type="checkbox" checked={value.idsEnabled} onChange={(event) => setDraft({ ...value, idsEnabled: event.target.checked })} /></label><label className="flex items-center justify-between gap-4 text-sm"><span><b>IPS simulation</b><span className="block text-xs text-[var(--color-text-muted)]">Show simulated response capability as enabled in browser state.</span></span><input type="checkbox" checked={value.ipsEnabled} onChange={(event) => setDraft({ ...value, ipsEnabled: event.target.checked })} /></label><div className="flex gap-5"><LabeledStatus value={value.idsEnabled ? "active" : "disabled"} /><LabeledStatus value={value.ipsEnabled ? "active" : "disabled"} /></div></div></Card>
      <Card className="p-5"><SectionTitle description="Shared monitoring preferences for the browser workflow.">Monitoring preferences</SectionTitle><label className="mt-4 block text-sm font-medium">Default history range<select className={inputClass} value={value.defaultHistoryRange} onChange={(event) => setDraft({ ...value, defaultHistoryRange: event.target.value as SystemPreferences["defaultHistoryRange"] })}><option value="24h">24 hours</option><option value="7d">7 days</option><option value="30d">30 days</option></select></label><label className="mt-4 block text-sm font-medium">Heart Rate Monitoring Interval<select className={inputClass} value={value.heartRateMonitoringIntervalSeconds} onChange={(event) => setDraft({ ...value, heartRateMonitoringIntervalSeconds: Number(event.target.value) as SystemPreferences["heartRateMonitoringIntervalSeconds"] })}><option value={15}>15 seconds</option><option value={30}>30 seconds</option><option value={60}>1 minute</option><option value={120}>2 minutes</option><option value={300}>5 minutes</option></select></label><label className="mt-4 flex items-center justify-between gap-4 text-sm"><span>Simulated notifications enabled</span><input type="checkbox" checked={value.notificationsEnabled} onChange={(event) => setDraft({ ...value, notificationsEnabled: event.target.checked })} /></label></Card>
      <Card className="p-5 lg:col-span-2"><SectionTitle description="Read-only context for the deterministic browser environment.">Network profile</SectionTitle><dl className="mt-4 grid gap-4 text-sm sm:grid-cols-3"><div><dt className="text-[var(--color-text-muted)]">Environment</dt><dd className="font-medium">Frontend-only simulation</dd></div><div><dt className="text-[var(--color-text-muted)]">Persistence</dt><dd className="font-medium">Browser localStorage</dd></div><div><dt className="text-[var(--color-text-muted)]">Monitoring network</dt><dd className="font-medium">Simulated private segment</dd></div></dl></Card>
      <div className="lg:col-span-2"><Button type="submit" disabled={saving}>Save simulated configuration</Button></div>
    </form>
  </section>;
}
