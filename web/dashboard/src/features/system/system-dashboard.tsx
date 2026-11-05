"use client";

import Link from "next/link";
import { useData } from "@/auth/session";
import { Metric, SectionTitle } from "@/components/ui/metric";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { formatAgo, formatDateTime } from "@/lib/date-time";
import { useResource } from "@/lib/use-resource";
import { AuditTable } from "./audit-table";

const plural = (n: number, noun: string) => `${n} ${noun}${n === 1 ? "" : "s"}`;

export function SystemDashboard() {
  const { data } = useData();
  const resource = useResource(
    async () => {
      const [organisations, devices, audit, revocation] = await Promise.all([
        data.registry.organisations(),
        data.registry.devices(),
        data.registry.audit(5),
        data.registry.revocation(),
      ]);
      return { organisations, devices, audit, revocation };
    },
    [],
  );

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Dashboard" description="The registry at a glance. The system administrator sees devices and organisations, never patient data. How devices are doing is for the organisation they are granted to." />
      <Loaded resource={resource} label="Loading the registry">
        {({ organisations, devices, audit, revocation }, { fetchedAt }) => {
          const count = (status: string) => devices.filter((d) => d.status === status).length;
          return (
            <>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                <Metric
                  label="Organisations"
                  value={organisations.length}
                  detail={`${organisations.filter((o) => o.status === "suspended").length} suspended`}
                />
                <Metric label="Active devices" value={count("active")} detail={`${plural(devices.filter((d) => d.type === "fixed_gateway").length, "gateway")}, ${plural(devices.filter((d) => d.type === "wearable").length, "wearable")} in all`} />
                <Metric label="Pending activation" value={count("pending")} detail="Registered, waiting for a credential or activation" />
                <Metric label="Suspended or revoked" value={count("suspended") + count("revoked")} detail={`${count("suspended")} suspended, ${count("revoked")} revoked`} />
                <Metric
                  label="Wearable revocation list"
                  value={revocation.published_version ? `v${revocation.published_version}` : "None"}
                  detail={revocation.published_version
                    ? `Published ${formatAgo(revocation.published_at)}${revocation.version > revocation.published_version ? `; v${revocation.version} waiting` : ""}`
                    : "No list published yet"}
                />
              </div>
              <SectionTitle actions={<Link className="text-sm text-[var(--color-info)] underline" href="/system/audit">Full audit log</Link>}>
                Latest registry changes
              </SectionTitle>
              <AuditTable events={audit} organisations={organisations} />
              <p className="text-xs text-[var(--color-text-muted)]">Loaded {formatDateTime(new Date(fetchedAt).toISOString())}.</p>
            </>
          );
        }}
      </Loaded>
    </section>
  );
}
