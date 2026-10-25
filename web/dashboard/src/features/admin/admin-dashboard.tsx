"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { SecurityEventTable } from "@/components/admin/security-event-table";
import { Card } from "@/components/ui/card";
import { PageIntro } from "@/components/ui/page-intro";
import { AdminPageError, AdminPageSkeleton } from "./admin-page-state";
import { LabeledStatus, Metric, SectionTitle } from "./admin-ui";
import { useAdminOverview } from "./use-admin-overview";

export function AdminDashboard() {
  const { state, refresh } = useAdminOverview();
  if (state.status === "loading") return <AdminPageSkeleton />;
  if (state.status === "error") return <AdminPageError message={state.message} onRetry={refresh} />;
  const { users, devices, stations, securityEvents } = state.data;
  const activeThreats = securityEvents.filter((event) => event.status === "active");
  const unresolved = securityEvents.filter((event) => event.status !== "resolved");
  const infrastructureHealthy = devices.every((device) => device.status === "online") && stations.every((station) => station.status === "online");
  return <section className="mx-auto max-w-7xl space-y-5">
    <PageIntro title="Organization Administrator Dashboard" description={`${state.data.organization.name} management, monitoring infrastructure, and security posture.`} />
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Metric label="Registered identities" value={users.length + devices.length + stations.length} detail={`${users.length} users · ${devices.length} wearables · ${stations.length} stations`} />
      <Metric label="Active devices" value={devices.filter((device) => device.status === "online").length} detail={`${devices.length} registered wearable devices`} />
      <Metric label="Monitoring Stations" value={stations.filter((station) => station.status === "online").length} detail={`${stations.length} registered · ${stations.filter((station) => station.status !== "online").length} require review`} />
      <Metric label="Unresolved security" value={unresolved.length} detail={`${activeThreats.length} active threat${activeThreats.length === 1 ? "" : "s"}`} />
    </div>
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="p-4"><SectionTitle description="Connectivity is separate from physiological monitoring state.">Infrastructure health</SectionTitle><dl className="mt-4 space-y-3 text-sm">
        <div className="flex justify-between gap-4"><dt>Overall state</dt><dd><LabeledStatus value={infrastructureHealthy ? "healthy" : "needs-review"} /></dd></div>
        <div className="flex justify-between gap-4"><dt>Wearables offline or disabled</dt><dd className="metric-number">{devices.filter((device) => ["offline", "disabled"].includes(device.status)).length}</dd></div>
        <div className="flex justify-between gap-4"><dt>Stations with limited, offline, or disabled connection</dt><dd className="metric-number">{stations.filter((station) => station.status !== "online").length}</dd></div>
      </dl></Card>
      <Card className="p-4"><SectionTitle>Administration tasks</SectionTitle><div className="mt-4 grid gap-2 sm:grid-cols-2">
        {[['Register wearable','/admin/devices/register'],['Manage identities','/admin/identities'],['Review IDS / IPS','/admin/security/ids-ips'],['Organization configuration','/admin/system-configuration']].map(([label, href]) => <Link key={href} className="group inline-flex min-h-11 items-center justify-between gap-3 rounded-[var(--radius-sm)] border border-[var(--color-brand)] bg-[var(--color-surface-subtle)] px-3 py-2 text-sm font-semibold text-[var(--color-brand)] transition-colors hover:bg-[var(--color-brand)] hover:text-[var(--color-on-brand)]" href={href}><span>{label}</span><ArrowRight className="shrink-0 transition-transform group-hover:translate-x-0.5" size={16} aria-hidden /></Link>)}
      </div></Card>
    </div>
    <div className="space-y-3"><SectionTitle description="Deterministic simulated detections; this is not a live security feed.">Recent security events</SectionTitle><SecurityEventTable events={securityEvents.slice().sort((a,b) => b.timestamp.localeCompare(a.timestamp)).slice(0,4)} compact /></div>
  </section>;
}
