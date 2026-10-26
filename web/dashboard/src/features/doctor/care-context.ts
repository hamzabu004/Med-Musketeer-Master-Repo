"use client";

import type { Alert, PatientSummary, Person } from "@/api/types";
import { useData } from "@/auth/session";
import { peopleById, personName } from "@/lib/people";
import { shortId } from "@/lib/labels";

/** How a doctor's screens name people: patients by pseudonym (and name, from the directory), and
 * whoever acknowledged an alert ("You" for the signed-in doctor). */
export function useCareNames(patients: PatientSummary[], people: Person[]) {
  const { session } = useData();
  const byId = peopleById(people);
  const patientById = new Map(patients.map((p) => [p.patient_id, p]));
  return {
    patient(alert: Pick<Alert, "patient_id">) {
      const p = patientById.get(alert.patient_id);
      return { label: p?.pseudonym ?? shortId(alert.patient_id), href: `/doctor/patients/${alert.patient_id}` };
    },
    patientName: (p: PatientSummary) => (p.user_id ? personName(byId.get(p.user_id)) : null),
    person: (userId: string) => (userId === session.userId ? "You" : (personName(byId.get(userId)) ?? `User ${shortId(userId)}`)),
  };
}
