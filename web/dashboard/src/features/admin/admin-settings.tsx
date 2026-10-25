"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageIntro } from "@/components/ui/page-intro";
import { services } from "@/services";
import { AdminPageError, AdminPageSkeleton } from "./admin-page-state";
import { LabeledStatus, SectionTitle } from "./admin-ui";
import { useAdminOverview } from "./use-admin-overview";

export function AdminSettings() {
  const { state, refresh } = useAdminOverview();
  const [message, setMessage] = useState("");
  const [working, setWorking] = useState(false);
  if (state.status === "loading") return <AdminPageSkeleton />;
  if (state.status === "error") return <AdminPageError message={state.message} onRetry={refresh} />;
  const data = state.data;

  async function notifications(enabled: boolean) {
    setWorking(true);
    await services.settings.save(data.session.organizationId, { ...data.preferences, notificationsEnabled: enabled });
    setMessage("Organization Administrator notification preference saved in this browser.");
    setWorking(false);
    refresh();
  }

  async function reset() {
    if (!window.confirm("Reset all persisted devices, assignments, security statuses, and preferences to the deterministic seed?")) return;
    setWorking(true);
    await services.demoState.resetDemoData();
    setMessage("Data reset to the original deterministic seed.");
    setWorking(false);
    refresh();
  }

  return (
    <section className="mx-auto max-w-5xl space-y-5">
      <PageIntro title="Organization Administrator Settings" description={`${data.organization.name} preferences and frontend environment controls.`} />
      {message && <p role="status" className="border-l-2 border-[var(--color-accent)] bg-[var(--color-accent-soft)] px-3 py-2 text-sm">{message}</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5"><SectionTitle description="Stored locally for this browser.">Organization Administrator preferences</SectionTitle><label className="mt-4 flex items-center justify-between gap-4 text-sm"><span>Simulated notifications</span><input type="checkbox" checked={data.preferences.notificationsEnabled} disabled={working} onChange={(event) => void notifications(event.target.checked)} /></label></Card>
        <Card className="p-5"><SectionTitle description="This environment has no backend, database, or production authentication provider.">Environment</SectionTitle><dl className="mt-4 space-y-3 text-sm"><div className="flex justify-between"><dt>Mode</dt><dd><LabeledStatus value="active" /></dd></div><div className="flex justify-between"><dt>Data source</dt><dd>Deterministic mock services</dd></div><div className="flex justify-between"><dt>Storage</dt><dd>Browser localStorage</dd></div><div className="flex justify-between"><dt>Authentication</dt><dd>Fixed accounts</dd></div></dl></Card>
        <Card className="border-[var(--color-critical)] p-5 lg:col-span-2"><SectionTitle description="Removes registered devices and all browser-state changes, then restores the exact initial seed. The current session remains signed in.">Reset Data</SectionTitle><Button className="mt-4" type="button" variant="danger" disabled={working} onClick={() => void reset()}>Reset Data</Button></Card>
      </div>
    </section>
  );
}
