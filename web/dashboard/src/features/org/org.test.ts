import { describe, expect, it } from "vitest";
import type { Account, PatientSummary, Person } from "@/api/types";
import { ApiError } from "@/api/errors";
import { loadPeople, personName } from "@/lib/people";
import { disableConsequences } from "./accounts";

const account = (role: string, user_id: string): Account => ({
  user_id, role, zitadel_sub: "z", status: "active", org_id: "o", patient_id: null, pseudonym: null, created_at: "2026-10-01T00:00:00Z",
});
const patient = (pseudonym: string, extra: Partial<PatientSummary>): PatientSummary => ({
  patient_id: pseudonym, pseudonym, user_id: null, account_status: "active", doctor_id: null, wearable_id: null, created_at: "2026-10-01T00:00:00Z", ...extra,
});

describe("disabling an account says what follows", () => {
  it("names the doctor's patients who lose their doctor", () => {
    const lines = disableConsequences(account("doctor", "d1"), [patient("P-1", { doctor_id: "d1" }), patient("P-2", { doctor_id: "d1" }), patient("P-3", { doctor_id: "d2" })]);
    expect(lines.join(" ")).toContain("2 patients (P-1, P-2) lose their doctor");
  });

  it("says a patient's wearable is returned only when they have one", () => {
    expect(disableConsequences(account("patient", "u1"), [patient("P-1", { user_id: "u1", wearable_id: "w" })]).join(" ")).toContain("wearable is returned");
    expect(disableConsequences(account("patient", "u1"), [patient("P-1", { user_id: "u1" })]).join(" ")).toContain("no wearable issued");
  });
});

describe("names from the directory", () => {
  it("keeps a page working with ids when the directory fails", async () => {
    expect(await loadPeople(() => Promise.reject(new ApiError(502, "identity provider error")))).toEqual({ people: [], named: false });
  });

  it("joins the parts ZITADEL returned, and has no name for a missing profile", () => {
    const person: Person = { user_id: "u", role: "doctor", status: "active", given_name: "Sarah", family_name: null, email: null };
    expect(personName(person)).toBe("Sarah");
    expect(personName({ ...person, given_name: null })).toBeNull();
    expect(personName(undefined)).toBeNull();
  });
});
