"use client";

import Link from "next/link";
import type { PatientSummary } from "@/api/types";
import { useData } from "@/auth/session";
import { Card } from "@/components/ui/card";
import { Metric, SectionTitle } from "@/components/ui/metric";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { Status, statusTone } from "@/components/ui/status";
import { formatDateTime } from "@/lib/date-time";
import { labelize } from "@/lib/labels";
import { loadPeople } from "@/lib/people";
import { useResource } from "@/lib/use-resource";
import { OrgAuditTable } from "./org-audit-table";

function Attention({ title, patients, fix }: { title: string; patients: PatientSummary[]; fix: string }) {
  return (
    <Card className="space-y-2 p-4">
      <h4 className="text-sm font-semibold">{title} ({patients.length})</h4>
      {patients.length ? (
        <ul className="flex flex-wrap gap-2 text-sm">
          {patients.map((p) => (
            <li key={p.patient_id}>
              <Link href={`/org/patients/${p.patient_id}`} className="text-[var(--color-info)] underline">{p.pseudonym}</Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-[var(--color-text-muted)]">None.</p>
      )}
      {patients.length > 0 && <p className="text-xs text-[var(--color-text-muted)]">{fix}</p>}
    </Card>
  );
}

export function OrgDashboard() {
  const { data } = useData();
  const resource = useResource(async () => {
    const [organisation, accounts, patients, devices, audit, { people }] = await Promise.all([
      data.organisation(),
      data.org.accounts(),
      data.patients(),
      data.devices(),
      data.org.audit(5),
      loadPeople(data.directory),
    ]);
    return { organisation, accounts, patients, devices, audit, people };
  }, []);

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <Loaded resource={resource} label="Loading your organisation">
        {({ organisation, accounts, patients, devices, audit, people }) => {
          const doctors = accounts.filter((a) => a.role === "doctor");
          const active = patients.filter((p) => p.account_status === "active");
          const wearables = devices.filter((d) => d.type === "wearable");
          const gateways = devices.filter((d) => d.type === "fixed_gateway");
          const issuable = wearables.filter((d) => d.status === "active" && d.patient_id === null);
          return (
            <>
              <PageIntro
                title={organisation.name}
                description={`${labelize(organisation.kind)} organisation. You manage its people, patients and wearables; ECG and alerts are for doctors only.`}
                actions={<Status label={labelize(organisation.status)} tone={statusTone(organisation.status)} />}
              />
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <Metric label="Doctors" value={doctors.filter((a) => a.status === "active").length} detail={`${doctors.filter((a) => a.status === "disabled").length} disabled`} />
                <Metric label="Patients" value={active.length} detail={`${patients.length - active.length} with a disabled account`} />
                <Metric label="Wearables issued" value={`${wearables.filter((d) => d.patient_id).length} / ${wearables.length}`} detail={`${issuable.length} active and free to issue`} />
                <Metric label="Fixed gateways" value={gateways.length} detail={`${gateways.filter((d) => d.status === "active").length} active`} />
              </div>
              <SectionTitle>Needs attention</SectionTitle>
              <div className="grid gap-3 md:grid-cols-2">
                <Attention title="Patients without a doctor" patients={active.filter((p) => !p.doctor_id)} fix="Assign a doctor on the patient's page: until then no one sees their alerts." />
                <Attention title="Patients without a wearable" patients={active.filter((p) => !p.wearable_id)} fix="Issue a wearable on the patient's page to start monitoring." />
              </div>
              <SectionTitle actions={<Link className="text-sm text-[var(--color-info)] underline" href="/org/audit">Full audit log</Link>}>
                Latest changes
              </SectionTitle>
              <OrgAuditTable events={audit} patients={patients} people={people} />
              {resource.status === "ready" && (
                <p className="text-xs text-[var(--color-text-muted)]">Loaded {formatDateTime(new Date(resource.fetchedAt).toISOString())}.</p>
              )}
            </>
          );
        }}
      </Loaded>
    </section>
  );
}
