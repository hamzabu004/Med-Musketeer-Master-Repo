/** Sample data in the shape of the cloud's tables. It holds the same people, devices and alerts as
 * `python -m app.manage seed-dev`, plus a second organisation so that out-of-reach answers (404)
 * can be seen. ECG samples are generated when a segment is read, not stored. */
import type {
  AuditEvent,
  CareAssignment,
  Credential,
  Device,
  Disorder,
  Grant,
  Organisation,
  SecurityEvent,
  WearableAssignment,
} from "@/api/types";
import type { Role } from "@/auth/roles";
import type { AttackTest, RecordingRequest } from "../contracts";

export interface MockUser {
  user_id: string;
  zitadel_sub: string;
  role: Role;
  status: "active" | "disabled";
  org_id: string | null;
  given_name: string;
  family_name: string;
  email: string;
  created_at: string;
}

export interface MockPatient {
  patient_id: string;
  user_id: string | null;
  org_id: string;
  pseudonym: string;
  created_at: string;
}

export interface MockSegment {
  segment_id: string;
  session_id: string;
  patient_id: string;
  device_id: string;
  kind: string;
  fs_hz: number;
  lead: string | null;
  started_at: string;
  ended_at: string | null;
  /** How to generate its ECG: beats per minute, an ectopic beat every n beats, a random seed. */
  signal: { bpm: number; ectopicEvery: number | null; seed: number };
  attested_by: string | null;
}

export interface MockClassification {
  classification_id: string;
  segment_id: string;
  source: string;
  model_version: string;
  label: string;
  confidence: number | null;
  created_at: string;
}

export interface MockAlert {
  alert_id: string;
  device_id: string;
  patient_id: string;
  classification_id: string | null;
  origin: string;
  created_at: string;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  /** The gateway that attested it (fixed path); null on the mobile path. */
  gateway_id: string | null;
}

/** A connectivity_events row (D17): a change of state of a device on a gateway; a gateway's own
 * rows have device_id = gateway_id. */
export interface MockConnectivityEvent {
  event_id: string;
  device_id: string;
  gateway_id: string;
  state: "online" | "offline";
  reason: string | null;
  at: string;
}

export interface World {
  organisations: Organisation[];
  users: MockUser[];
  patients: MockPatient[];
  devices: Device[];
  credentials: Credential[];
  grants: Grant[];
  careAssignments: CareAssignment[];
  wearableAssignments: WearableAssignment[];
  disorders: Disorder[];
  segments: MockSegment[];
  classifications: MockClassification[];
  alerts: MockAlert[];
  connectivity: MockConnectivityEvent[];
  securityEvents: SecurityEvent[];
  audit: AuditEvent[];
  attackTests: AttackTest[];
  recordings: RecordingRequest[];
  exports: number;
  /** The wearable revocation list's version (D16); sample data publishes every version at once. */
  revocation: { version: number; published_at: string };
}

/** A deterministic UUID-shaped id, so links into sample data stay valid across reloads. */
export function mockId(kind: number, n: number): string {
  const hex = (value: number, width: number) => value.toString(16).padStart(width, "0");
  // The record number leads, since screens show a UUID's first block.
  return `${hex(n * 0x9e37 + kind, 8).slice(-8)}-${hex(kind, 4)}-4000-8000-${hex(n, 12)}`;
}

const ID = { org: 1, user: 2, patient: 3, device: 4, credential: 5, grant: 6, care: 7, segment: 8, session: 9, classification: 10, alert: 11, security: 12, audit: 13, attack: 14, command: 15, connectivity: 16 };

export function createWorld(now = Date.now()): World {
  const at = (minutesAgo: number) => new Date(now - minutesAgo * 60_000).toISOString();
  const created = at(60 * 24 * 30);
  let counter = 1000;
  const next = (kind: number) => mockId(kind, counter++);

  const devHospital = mockId(ID.org, 1);
  const northside = mockId(ID.org, 2);
  const organisations: Organisation[] = [
    { org_id: devHospital, name: "Dev Hospital", kind: "public", status: "active", zitadel_org_id: "z-org-1", registered_by: mockId(ID.user, 1), created_at: created },
    { org_id: northside, name: "Northside Clinic", kind: "private", status: "active", zitadel_org_id: "z-org-2", registered_by: mockId(ID.user, 1), created_at: created },
  ];

  const person = (n: number, role: Role, org: string | null, given: string, family: string, key: string): MockUser => ({
    user_id: mockId(ID.user, n), zitadel_sub: `z-user-${n}`, role, status: "active", org_id: org,
    given_name: given, family_name: family, email: `${key}@medmusketeer.example`, created_at: created,
  });
  const users: MockUser[] = [
    person(1, "system_admin", null, "Sana", "Sysadmin", "sysadmin"),
    person(2, "org_admin", devHospital, "Omar", "Admin", "orgadmin"),
    person(3, "doctor", devHospital, "Sarah", "Ahmed", "doctor1"),
    person(4, "doctor", devHospital, "Bilal", "Raza", "doctor2"),
    person(5, "patient", devHospital, "Ali", "Khan", "patient1"),
    person(6, "patient", devHospital, "Fatima", "Noor", "patient2"),
    person(7, "patient", devHospital, "Usman", "Iqbal", "patient3"),
    person(8, "org_admin", northside, "Nadia", "Malik", "northside-admin"),
    person(9, "doctor", northside, "Hassan", "Shah", "northside-doctor"),
    person(10, "patient", northside, "Ayesha", "Siddiqui", "northside-patient"),
  ];
  const [sysadmin, orgadmin, doctor1, doctor2, , , , nsAdmin, nsDoctor] = users.map((user) => user.user_id);

  const patientRow = (n: number, userN: number, org: string, pseudonym: string): MockPatient => ({
    patient_id: mockId(ID.patient, n), user_id: mockId(ID.user, userN), org_id: org, pseudonym, created_at: created,
  });
  const patients = [
    patientRow(1, 5, devHospital, "P-1001"),
    patientRow(2, 6, devHospital, "P-1002"),
    patientRow(3, 7, devHospital, "P-1003"),
    patientRow(4, 10, northside, "N-2001"),
  ];
  const [p1, p2, p3, p4] = patients.map((patient) => patient.patient_id);

  const devices: Device[] = [];
  const credentials: Credential[] = [];
  const grants: Grant[] = [];
  const device = (n: number, type: string, org: string | null, status: Device["status"] = "active"): string => {
    const device_id = mockId(ID.device, n);
    devices.push({ device_id, type, status, is_testbed: true, current_mode: "unknown", current_gateway_id: null, last_seen: null,
      status_changed_at: created, revocation_version: null, registered_by: sysadmin, created_at: created });
    if (status !== "pending") {
      credentials.push({
        credential_id: mockId(ID.credential, n), device_id, auth_method: "x509_mtls", key_type: "ec_p256",
        credential_ref: (n.toString(16).padStart(2, "0") + "A1B2C3D4E5F6").repeat(5).slice(0, 64).toUpperCase(),
        status: "active", created_at: created, expires_at: null, metadata: {},
      });
    }
    if (org) grants.push({ grant_id: mockId(ID.grant, n), device_id, org_id: org, granted_by: sysadmin, granted_at: created, revoked_by: null, revoked_at: null });
    return device_id;
  };
  const gateway = device(1, "fixed_gateway", devHospital);
  const wearables = [2, 3, 4, 5].map((n) => device(n, "wearable", devHospital));
  const nsWearable = device(6, "wearable", northside);
  device(7, "wearable", null, "pending"); // registered, no credential yet: for the registry screens
  // Gateways report the revocation list version they enforce; Northside's is behind, so the
  // system admin's screens show the stale-list flag.
  const nsGateway = device(8, "fixed_gateway", northside);
  Object.assign(devices.find((d) => d.device_id === gateway)!, { revocation_version: 2 });
  Object.assign(devices.find((d) => d.device_id === nsGateway)!, { revocation_version: 1 });

  const live = (deviceId: string, mode: string, via: string | null, seenMinutesAgo: number) => {
    Object.assign(devices.find((d) => d.device_id === deviceId)!, { current_mode: mode, current_gateway_id: via, last_seen: at(seenMinutesAgo) });
  };
  live(gateway, "fixed", null, 0.33);
  live(wearables[0], "fixed", gateway, 0.67); // patient1 on the fixed path
  live(wearables[1], "mobile", null, 6); // patient2 on the mobile path
  live(nsWearable, "mobile", null, 2);
  live(nsGateway, "fixed", null, 1);

  // Connectivity log, as seed-dev writes it: the gateway was down for 20 minutes this morning and
  // has been up since; patient1's wearable joined it after, patient2's left it for the mobile path.
  const connectivity: MockConnectivityEvent[] = ([
    [gateway, gateway, "online", null, 60 * 26], [wearables[1], gateway, "online", null, 60 * 25],
    [wearables[1], gateway, "offline", "mode_switch", 60 * 8], [gateway, gateway, "offline", null, 60 * 3 + 40],
    [gateway, gateway, "online", null, 60 * 3 + 20], [wearables[0], gateway, "online", null, 60 * 3 + 15],
    [nsGateway, nsGateway, "online", null, 60 * 50],
  ] as const).map(([device_id, gateway_id, state, reason, minutesAgo], i) => ({
    event_id: mockId(ID.connectivity, i + 1), device_id, gateway_id, state, reason, at: at(minutesAgo),
  }));

  const careAssignments: CareAssignment[] = [
    [p1, doctor1, orgadmin], [p2, doctor1, orgadmin], [p3, doctor2, orgadmin], [p4, nsDoctor, nsAdmin],
  ].map(([patient_id, doctor_id, assigned_by], i) => ({
    assignment_id: mockId(ID.care, i + 1), patient_id, doctor_id, assigned_by, valid_from: at(60 * 24 * 20), valid_to: null,
  }));

  const disorders: Disorder[] = [
    [p1, "Premature ventricular contractions", orgadmin], [p2, "Paroxysmal atrial fibrillation", orgadmin],
    [p3, "Hypertension", orgadmin], [p4, "Sinus tachycardia", nsAdmin],
  ].map(([patient_id, disorder, recorded_by]) => ({ patient_id, disorder, recorded_by, recorded_at: at(60 * 24 * 19) }));

  const wearableAssignments: WearableAssignment[] = [];
  const segments: MockSegment[] = [];
  const classifications: MockClassification[] = [];
  const alerts: MockAlert[] = [];

  // (patient, wearable, path, issued by, doctor who acknowledges,
  //  alerts as [minutes ago, label, confidence, ectopic every n beats, bpm, acknowledged])
  type Event = [number, string, number, number | null, number, boolean];
  const monitored: [string, string, "fixed" | "mobile", string, string, Event[]][] = [
    [p1, wearables[0], "fixed", orgadmin, doctor1, [[5, "V", 0.94, 4, 78, false], [95, "V", 0.81, 6, 74, true], [400, "N", 0.62, null, 70, true]]],
    [p2, wearables[1], "mobile", orgadmin, doctor1, [[30, "S", 0.77, 5, 96, false], [720, "F", 0.58, 7, 88, false]]],
    [p4, nsWearable, "mobile", nsAdmin, nsDoctor, [[50, "V", 0.88, 5, 82, false]]],
  ];
  let seed = 1;
  for (const [patient_id, device_id, path, issuer, acknowledger, events] of monitored) {
    wearableAssignments.push({ device_id, patient_id, issued_by: issuer, assigned_at: at(60 * 48), unassigned_at: null });
    const session_id = next(ID.session);
    for (const [minutesAgo, label, confidence, ectopicEvery, bpm, acknowledged] of events) {
      const start = now - minutesAgo * 60_000;
      const segment_id = next(ID.segment);
      segments.push({
        segment_id, session_id, patient_id, device_id, kind: "alert", fs_hz: 360, lead: "MLII",
        started_at: new Date(start).toISOString(), ended_at: new Date(start + 10_000).toISOString(),
        signal: { bpm, ectopicEvery, seed: seed++ }, attested_by: path === "fixed" ? gateway : null,
      });
      classifications.push({
        classification_id: next(ID.classification), segment_id, source: "wearable", model_version: "tinydl-screen-0.1",
        label: "abnormal", confidence: Math.min(0.99, confidence + 0.05), created_at: new Date(start + 10_000).toISOString(),
      });
      const classification_id = next(ID.classification);
      classifications.push({
        classification_id, segment_id, source: path === "fixed" ? "gateway" : "cloud", model_version: "aami-cnn-0.1",
        label, confidence, created_at: new Date(start + 11_000).toISOString(),
      });
      alerts.push({
        alert_id: next(ID.alert), device_id, patient_id, classification_id, origin: path === "fixed" ? "gateway" : "cloud",
        created_at: new Date(start + 11_000).toISOString(),
        acknowledged_by: acknowledged ? acknowledger : null, acknowledged_at: acknowledged ? new Date(start + 12 * 60_000).toISOString() : null,
        gateway_id: path === "fixed" ? gateway : null,
      });
    }
  }

  // A finished on-demand recording of patient1 (30 s on the fixed path), so the viewer has one.
  const recordedAt = now - 120 * 60_000;
  const recordingSegment = next(ID.segment);
  segments.push({
    segment_id: recordingSegment, session_id: next(ID.session), patient_id: p1, device_id: wearables[0], kind: "recording", fs_hz: 360, lead: "MLII",
    started_at: new Date(recordedAt + 4_000).toISOString(), ended_at: new Date(recordedAt + 34_000).toISOString(),
    signal: { bpm: 72, ectopicEvery: 9, seed: seed++ }, attested_by: gateway,
  });
  const recordings: RecordingRequest[] = [{
    command_id: mockId(ID.command, 1), patient_id: p1, device_id: wearables[0], issued_by: doctor1, type: "ecg_recording", path: "fixed",
    status: "acked", created_at: new Date(recordedAt).toISOString(), acked_at: new Date(recordedAt + 3_000).toISOString(), duration_s: 30, segment_id: recordingSegment,
  }];

  const securityEvents: SecurityEvent[] = ([
    [3, wearables[2], "ids", "dos_flood", "detected", null, null],
    [50, null, "ips", "port_scan", "blocked", "drop_source", "applied"],
    [300, wearables[0], "ids", "benign", "no_threat", null, null],
  ] as const).map(([minutesAgo, device_id, mode, predicted_class, outcome, action, action_result], i) => ({
    event_id: mockId(ID.security, i + 1), ts: at(minutesAgo), gateway_id: gateway, device_id, mode, predicted_class, outcome, action, action_result,
  }));

  // A finished attack test whose window holds the dos_flood detection above.
  const attackTests: AttackTest[] = [{
    test_id: mockId(ID.attack, 1), target_device_id: wearables[2], triggered_by: sysadmin, attack_type: "dos_flood",
    parameters: { rate_pps: 500, duration_s: 120 }, started_at: at(4), ended_at: at(2),
  }];

  const audit: AuditEvent[] = [];
  const log = (minutesAgo: number, actor_id: string, scope: string, action: string, org_id: string | null, target_id: string | null, details = {}) =>
    audit.push({ event_id: next(ID.audit), at: at(minutesAgo), actor_id, scope, org_id, action, target_id, details });
  for (const org of organisations) log(60 * 24 * 30, sysadmin, "registry", "organisation.created", org.org_id, org.org_id, { name: org.name });
  for (const admin of users.filter((u) => u.role === "org_admin")) log(60 * 24 * 30 - 5, sysadmin, "registry", "account.created", admin.org_id, admin.user_id, { role: "org_admin" });
  for (const d of devices) log(60 * 24 * 29, sysadmin, "registry", "device.registered", null, d.device_id, { type: d.type });
  for (const g of grants) log(60 * 24 * 28, sysadmin, "registry", "grant.created", g.org_id, g.device_id, { grant_id: g.grant_id });
  for (const c of careAssignments) {
    const org = patients.find((p) => p.patient_id === c.patient_id)!.org_id;
    log(60 * 24 * 20, c.assigned_by, "organisation", "doctor.assigned", org, c.patient_id, { doctor_id: c.doctor_id, previous_doctor_id: null });
  }
  for (const w of wearableAssignments) {
    const org = patients.find((p) => p.patient_id === w.patient_id)!.org_id;
    log(60 * 48, w.issued_by, "organisation", "wearable.issued", org, w.patient_id, { device_id: w.device_id });
  }

  return {
    organisations, users, patients, devices, credentials, grants, careAssignments, wearableAssignments,
    disorders, segments, classifications, alerts, connectivity, securityEvents, audit, attackTests, recordings, exports: 0,
    revocation: { version: 2, published_at: at(60 * 3) },
  };
}
