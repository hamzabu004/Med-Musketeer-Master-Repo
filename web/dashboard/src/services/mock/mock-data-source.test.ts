import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiError } from "@/api/errors";
import { stitchChunks } from "@/lib/ecg";
import { createMockDataSource, principalOf } from "./mock-data-source";
import { createWorld, type World } from "./world";

/** Sample data must answer as the API does (D9, TC-C09): a screen tested in sample mode then
 * behaves the same against the cloud. */
let world: World;
const as = (email: string) => {
  const user = world.users.find((u) => u.email.startsWith(`${email}@`))!;
  return createMockDataSource(world, principalOf(world, user));
};
const statusOf = (promise: Promise<unknown>) => promise.then(() => 200, (error: ApiError) => error.status);
const patientId = (pseudonym: string) => world.patients.find((p) => p.pseudonym === pseudonym)!.patient_id;

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true, advanceTimeDelta: 200 });
  world = createWorld(Date.parse("2026-10-25T12:00:00Z"));
});

describe("sample data, D9", () => {
  it("refuses each role the endpoint groups it may not call (403)", async () => {
    expect(await statusOf(as("orgadmin").care.alerts())).toBe(403); // no ECG, alerts for the org admin
    expect(await statusOf(as("orgadmin").registry.devices())).toBe(403);
    expect(await statusOf(as("sysadmin").patients())).toBe(403); // no patient data for the system admin
    expect(await statusOf(as("sysadmin").directory())).toBe(403);
    expect(await statusOf(as("doctor1").org.accounts())).toBe(403);
    expect(await statusOf(as("patient1").patients())).toBe(403);
    expect(await statusOf(as("patient1").care.acknowledge(world.alerts[0].alert_id))).toBe(403);
  });

  it("answers 404 for a patient out of reach, as for one that does not exist", async () => {
    expect(await statusOf(as("doctor2").care.patientAlerts(patientId("P-1001")))).toBe(404); // not their patient
    expect(await statusOf(as("orgadmin").disorders(patientId("N-2001")))).toBe(404); // another organisation
    expect(await statusOf(as("patient1").care.segments(patientId("P-1002")))).toBe(404); // someone else
    expect(await statusOf(as("doctor1").care.patientAlerts("00000000-0000-4000-8000-00000000dead"))).toBe(404);
  });

  it("scopes lists: a doctor sees their own patients, a patient their own alerts", async () => {
    expect((await as("doctor1").patients()).map((p) => p.pseudonym)).toEqual(["P-1001", "P-1002"]);
    expect((await as("orgadmin").patients()).map((p) => p.pseudonym)).toEqual(["P-1001", "P-1002", "P-1003"]);
    const own = await as("patient1").care.alerts();
    expect(own.length).toBe(3);
    expect(new Set(own.map((a) => a.patient_id))).toEqual(new Set([patientId("P-1001")]));
    expect((await as("doctor1").care.alerts({ unacknowledged: true })).map((a) => a.label)).toEqual(["V", "S", "F"]);
  });

  it("shows e-mail in the directory to the org admin only, and a patient their doctor", async () => {
    const forAdmin = await as("orgadmin").directory();
    expect(forAdmin.every((p) => p.email)).toBe(true);
    const forPatient = await as("patient1").directory();
    expect(forPatient.map((p) => `${p.given_name} ${p.role}`).sort()).toEqual(["Ali patient", "Sarah doctor"]);
    expect(forPatient.every((p) => p.email === null)).toBe(true);
  });
});

describe("sample data, state rules", () => {
  it("lets a doctor acknowledge once", async () => {
    const doctor = as("doctor1");
    const [alert] = await doctor.care.alerts({ unacknowledged: true });
    const acknowledged = await doctor.care.acknowledge(alert.alert_id);
    expect(acknowledged.acknowledged_by).toBe(world.users.find((u) => u.email.startsWith("doctor1@"))!.user_id);
    expect(await statusOf(doctor.care.acknowledge(alert.alert_id))).toBe(409);
  });

  it("returns an invite code once and refuses a duplicate pseudonym", async () => {
    const admin = as("orgadmin");
    const created = await admin.org.createAccount({ role: "patient", email: "new@x.example", given_name: "N", family_name: "P", pseudonym: "P-1004" });
    expect(created.invite_code).toMatch(/^[A-Z2-9]{6}$/);
    expect((await admin.org.accounts()).find((a) => a.user_id === created.user_id)).not.toHaveProperty("invite_code");
    expect(await statusOf(admin.org.createAccount({ role: "patient", email: "b@x.example", given_name: "B", family_name: "P", pseudonym: "P-1004" }))).toBe(409);
  });

  it("ends a disabled doctor's care assignments and returns a disabled patient's wearable", async () => {
    const admin = as("orgadmin");
    const doctor1 = world.users.find((u) => u.email.startsWith("doctor1@"))!;
    await admin.org.disableAccount(doctor1.user_id);
    expect((await admin.patients()).filter((p) => p.doctor_id === doctor1.user_id)).toEqual([]);
    const patient1 = world.users.find((u) => u.email.startsWith("patient1@"))!;
    await admin.org.disableAccount(patient1.user_id);
    expect((await admin.patients()).find((p) => p.pseudonym === "P-1001")!.wearable_id).toBeNull();
    expect(await statusOf(admin.org.assignDoctor(patientId("P-1001"), world.users.find((u) => u.email.startsWith("doctor2@"))!.user_id))).toBe(409);
  });

  it("issues only an active, granted, unassigned wearable", async () => {
    const admin = as("orgadmin");
    const free = (await admin.devices()).find((d) => d.type === "wearable" && d.patient_id === null)!;
    const gateway = (await admin.devices()).find((d) => d.type === "fixed_gateway")!;
    expect(await statusOf(admin.org.issueWearable(patientId("P-1003"), gateway.device_id))).toBe(422);
    const elsewhere = world.devices.find((d) => d.type === "wearable" && world.grants.some((g) => g.device_id === d.device_id && g.org_id !== world.organisations[0].org_id))!;
    expect(await statusOf(admin.org.issueWearable(patientId("P-1003"), elsewhere.device_id))).toBe(404);
    await admin.org.issueWearable(patientId("P-1003"), free.device_id);
    expect(await statusOf(admin.org.issueWearable(patientId("P-1002"), free.device_id))).toBe(409);
  });

  it("follows the registry lifecycle: a credential before activation, revoke cascades", async () => {
    const sys = as("sysadmin");
    const deviceId = "11111111-2222-4333-8444-555555555555";
    await sys.registry.registerDevice({ device_id: deviceId, type: "wearable", is_testbed: true });
    expect(await statusOf(sys.registry.activateDevice(deviceId))).toBe(409);
    expect(await statusOf(sys.registry.addCredential(deviceId, { auth_method: "x509_mtls", credential_ref: "not-hex" }))).toBe(422);
    const credential = await sys.registry.addCredential(deviceId, { auth_method: "x509_mtls", credential_ref: "ab:".repeat(32).slice(0, -1) });
    expect(credential.credential_ref).toBe("AB".repeat(32));
    expect((await sys.registry.activateDevice(deviceId)).status).toBe("active");
    await sys.registry.grantDevice(deviceId, world.organisations[0].org_id);
    await sys.registry.revokeDevice(deviceId);
    expect((await sys.registry.credentials(deviceId)).every((c) => c.status === "revoked")).toBe(true);
    expect((await sys.registry.grants(deviceId)).every((g) => g.revoked_at !== null)).toBe(true);
  });

  it("serves a segment's ECG as int16le-base64 chunks at fs_hz", async () => {
    const doctor = as("doctor1");
    const [alert] = await doctor.care.alerts();
    const segment = await doctor.care.segment(alert.segment_id!);
    expect(segment.chunks).toHaveLength(10);
    const samples = stitchChunks(segment.chunks);
    expect(samples.length).toBe(10 * segment.fs_hz);
    expect(Math.max(...samples)).toBeGreaterThan(150); // R peaks, about 1 mV at 200 counts per mV
    expect(segment.classifications.map((c) => c.source).sort()).toEqual(["gateway", "wearable"]);
    expect(await statusOf(as("doctor2").care.segment(alert.segment_id!))).toBe(404);
  });
});

describe("sample data, review findings (Phase 3)", () => {
  it("refuses a duplicate disorder and a pseudonym for a doctor, as the API does", async () => {
    const admin = as("orgadmin");
    expect(await statusOf(admin.org.recordDisorder(patientId("P-1001"), "Premature ventricular contractions"))).toBe(409);
    expect(await statusOf(admin.org.createAccount({ role: "doctor", email: "d@x.example", given_name: "D", family_name: "R", pseudonym: "X-1" }))).toBe(422);
  });

  it("shows the org admin registry actions on their organisation in its audit log", async () => {
    const free = world.devices.find((d) => d.status === "pending")!;
    const sys = as("sysadmin");
    await sys.registry.addCredential(free.device_id, { auth_method: "x509_mtls", credential_ref: "CD".repeat(32) });
    await sys.registry.grantDevice(free.device_id, world.organisations[0].org_id);
    const actions = (await as("orgadmin").org.audit()).map((e) => e.action);
    expect(actions).toContain("grant.created");
  });
});

describe("sample data, suspension", () => {
  it("refuses every member of a suspended organisation, as auth.get_principal does", async () => {
    await as("sysadmin").registry.setOrganisationStatus(world.organisations[0].org_id, "suspended");
    expect(await statusOf(as("doctor1").me())).toBe(403);
    expect(await statusOf(as("orgadmin").patients())).toBe(403);
    expect(await statusOf(as("northside-doctor").patients())).toBe(200); // other organisations are unaffected
    expect(await statusOf(as("sysadmin").registry.organisations())).toBe(200);
  });
});

describe("sample data, attack tests", () => {
  it("refuses a production device and a second run against the same device", async () => {
    const sys = as("sysadmin");
    const production = "22222222-3333-4444-8555-666666666666";
    await sys.registry.registerDevice({ device_id: production, type: "wearable", is_testbed: false });
    expect(await statusOf(sys.attackTests.start({ attack_type: "syn_flood", target_device_id: production, params: {} }))).toBe(409);
    const testbed = world.devices.find((d) => d.is_testbed && d.status === "active")!.device_id;
    const run = await sys.attackTests.start({ attack_type: "syn_flood", target_device_id: testbed, params: { rate_pps: 100 } });
    expect(await statusOf(sys.attackTests.start({ attack_type: "port_scan", target_device_id: testbed, params: {} }))).toBe(409);
    expect((await sys.attackTests.stop(run.test_id)).ended_at).not.toBeNull();
    expect(await statusOf(as("orgadmin").attackTests.list())).toBe(403);
  });
});
