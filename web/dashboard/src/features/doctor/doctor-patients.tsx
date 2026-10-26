"use client";

import Link from "next/link";
import type { Alert, OrgDevice, PatientSummary, Person } from "@/api/types";
import { useData } from "@/auth/session";
import { EmptyState } from "@/components/ui/empty-state";
import { Loaded } from "@/components/ui/page-state";
import { PageIntro } from "@/components/ui/page-intro";
import { Table, Td, THead, Tr } from "@/components/ui/table";
import { formatAgo } from "@/lib/date-time";
import { labelize } from "@/lib/labels";
import { loadPeople, NAMES_UNAVAILABLE } from "@/lib/people";
import { useResource } from "@/lib/use-resource";
import { useCareNames } from "./care-context";

export function DoctorPatients() {
  const { data } = useData();
  const resource = useResource(async () => {
    const [patients, devices, open, { people, named }] = await Promise.all([
      data.patients(), data.devices(), data.care.alerts({ unacknowledged: true, limit: 1000 }), loadPeople(data.directory),
    ]);
    return { patients, devices, open, people, named };
  }, []);

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro title="Patients" description="The patients you care for. The organisation administrator assigns patients to you." />
      <Loaded resource={resource} label="Loading your patients">
        {({ patients, devices, open, people, named }) => <List patients={patients} devices={devices} open={open} people={people} named={named} />}
      </Loaded>
    </section>
  );
}

function List({ patients, devices, open, people, named }: {
  patients: PatientSummary[];
  devices: OrgDevice[];
  open: Alert[];
  people: Person[];
  named: boolean;
}) {
  const names = useCareNames(patients, people);
  if (!patients.length) return <EmptyState title="No patients yet" description="Patients appear here once the organisation administrator assigns them to you." />;
  return (
    <>
      {!named && <p className="text-xs text-[var(--color-text-muted)]">{NAMES_UNAVAILABLE}</p>}
      <Table label="Patients" minWidth={760}>
        <THead columns={["Pseudonym", "Name", "Unacknowledged alerts", "Wearable path", "Last heard from"]} />
        <tbody>
          {patients.map((p) => {
            const wearable = devices.find((d) => d.device_id === p.wearable_id);
            const count = open.filter((a) => a.patient_id === p.patient_id).length;
            return (
              <Tr key={p.patient_id}>
                <Td><Link href={`/doctor/patients/${p.patient_id}`} className="font-medium text-[var(--color-info)] underline-offset-2 hover:underline">{p.pseudonym}</Link></Td>
                <Td>{names.patientName(p) ?? "—"}</Td>
                <Td className={count ? "font-semibold text-[var(--color-critical)]" : "text-[var(--color-text-muted)]"}>{count}</Td>
                <Td>{wearable ? labelize(wearable.current_mode) : <span className="text-[var(--color-text-muted)]">No wearable</span>}</Td>
                <Td>{wearable ? formatAgo(wearable.last_seen) : "—"}</Td>
              </Tr>
            );
          })}
        </tbody>
      </Table>
    </>
  );
}
