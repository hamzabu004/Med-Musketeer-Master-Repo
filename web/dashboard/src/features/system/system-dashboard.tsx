"use client";

import Link from "next/link";
import { useData } from "@/auth/session";
import { Metric, SectionTitle } from "@/components/ui/metric";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { formatDateTime } from "@/lib/date-time";
import { useResource } from "@/lib/use-resource";
import { AuditTable } from "./audit-table";
import { SecurityEventTable } from "./security-event-table";

const plural = (n: number, noun: string) => `${n} ${noun}${n === 1 ? "" : "s"}`;

export function SystemDashboard() {
  const { data } = useData();
  const resource = useResource(
    async () => {
      const [organisations, devices, events, audit] = await Promise.all([
        data.registry.organisations(),
        data.registry.devices(),
        data.registry.securityEvents(5),
        data.registry.audit(5),
      ]);
      return { organisations, devices, events, audit };
    },
    [],
  );

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Dashboard" description="The registry at a glance. The system administrator sees devices and organisations, never patient data." />
      <Loaded resource={resource} label="Loading the registry">
        {({ organisations, devices, events, audit }) => {
          const count = (status: string) => devices.filter((d) => d.status === status).length;
          return (
            <>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <Metric
                  label="Organisations"
                  value={organisations.length}
                  detail={`${organisations.filter((o) => o.status === "suspended").length} suspended`}
                />
                <Metric label="Active devices" value={count("active")} detail={`${plural(devices.filter((d) => d.type === "fixed_gateway").length, "gateway")}, ${plural(devices.filter((d) => d.type === "wearable").length, "wearable")} in all`} />
                <Metric label="Pending activation" value={count("pending")} detail="Registered, waiting for a credential or activation" />
                <Metric label="Suspended or revoked" value={count("suspended") + count("revoked")} detail={`${count("suspended")} suspended, ${count("revoked")} revoked`} />
              </div>
              <SectionTitle actions={<Link className="text-sm text-[var(--color-info)] underline" href="/system/security-events">All security events</Link>}>
                Latest security events
              </SectionTitle>
              <SecurityEventTable events={events} empty="No security events reported by the gateways." />
              <SectionTitle actions={<Link className="text-sm text-[var(--color-info)] underline" href="/system/audit">Full audit log</Link>}>
                Latest registry changes
              </SectionTitle>
              <AuditTable events={audit} organisations={organisations} />
              <p className="text-xs text-[var(--color-text-muted)]">Loaded {formatDateTime(new Date().toISOString())}.</p>
            </>
          );
        }}
      </Loaded>
    </section>
  );
}
