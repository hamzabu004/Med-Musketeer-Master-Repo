/** The sample-data source: the cloud API's behaviour over the in-browser world. It applies the D9
 * rules the API applies (403 for a role that may not call an endpoint, 404 for a patient outside the
 * caller's reach) and the same state rules (409/422), so screens behave alike in both modes. */
import { ApiError } from "@/api/errors";
import type { Account, Alert, AuditEvent, Me, NewAccount, PatientSummary, Person, SegmentDetail } from "@/api/types";
import type { Role } from "@/auth/roles";
import { encodeSamples } from "@/lib/ecg";
import type { AlertQuery, AttackTest, DataSource, RecordingRequest } from "../contracts";
import { FS_HZ, seededRandom, syntheticEcg } from "./synthetic-ecg";
import type { MockPatient, MockUser, World } from "./world";

export interface Principal {
  user_id: string;
  role: Role;
  org_id: string | null;
  patient_id: string | null;
}

export function principalOf(world: World, user: MockUser): Principal {
  return {
    user_id: user.user_id, role: user.role, org_id: user.org_id,
    patient_id: world.patients.find((p) => p.user_id === user.user_id)?.patient_id ?? null,
  };
}

const forbidden = () => new ApiError(403, "not allowed for this role", "not allowed for this role");
const notFound = (what: string) => new ApiError(404, `${what} not found`, `${what} not found`);
const conflict = (message: string) => new ApiError(409, message, message);
const invalid = (message: string) => new ApiError(422, message, message);

/** Answers are copies, so a screen cannot change the world by editing what it got. */
const copy = <T>(value: T): T => structuredClone(value);
const delay = () => new Promise((resolve) => setTimeout(resolve, 120));

/** `onChange` runs after every write, so the caller can persist the world. */
export function createMockDataSource(world: World, principal: Principal, onChange: () => void = () => {}): DataSource {
  const now = () => new Date().toISOString();
  let counter = 0;
  const newId = () => crypto.randomUUID?.() ?? `00000000-0000-4000-8000-${(Date.now() + counter++).toString(16).padStart(12, "0")}`;

  async function answer<T>(roles: Role[], run: () => T, write = false): Promise<T> {
    await delay();
    // auth.get_principal: members of a suspended organisation are refused on every call.
    if (principal.org_id && world.organisations.find((o) => o.org_id === principal.org_id)?.status !== "active") {
      throw new ApiError(403, "organisation suspended", "organisation suspended");
    }
    if (!roles.includes(principal.role)) throw forbidden();
    const result = run();
    if (write) onChange();
    return copy(result);
  }

  function audit(scope: string, action: string, org_id: string | null, target_id: string | null, details: Record<string, unknown> = {}) {
    world.audit.push({ event_id: newId(), at: now(), actor_id: principal.user_id, scope, org_id, action, target_id, details });
  }

  const currentDoctor = (patientId: string) =>
    world.careAssignments.find((c) => c.patient_id === patientId && c.valid_to === null)?.doctor_id ?? null;
  const currentWearable = (patientId: string) =>
    world.wearableAssignments.find((w) => w.patient_id === patientId && w.unassigned_at === null) ?? null;
  const accountStatus = (patient: MockPatient) => world.users.find((u) => u.user_id === patient.user_id)?.status ?? null;

  /** The patient, if the caller may see them (organisation.patient_in_scope); otherwise 404. */
  function patientInScope(patientId: string): MockPatient {
    const patient = world.patients.find((p) => p.patient_id === patientId && p.org_id === principal.org_id);
    const reachable =
      patient &&
      (principal.role === "org_admin" ||
        (principal.role === "doctor" && currentDoctor(patient.patient_id) === principal.user_id) ||
        (principal.role === "patient" && patient.user_id === principal.user_id));
    if (!reachable) throw notFound("patient");
    return patient;
  }

  function requireActiveAccount(patient: MockPatient) {
    if (accountStatus(patient) === "disabled") throw conflict("the patient's account is disabled");
  }

  function endWearableAssignment(patientId: string) {
    const open = currentWearable(patientId);
    if (open) open.unassigned_at = now();
    return open;
  }

  function closeGrant(grantId: string) {
    const grant = world.grants.find((g) => g.grant_id === grantId)!;
    Object.assign(grant, { revoked_at: now(), revoked_by: principal.user_id });
    audit("registry", "grant.revoked", grant.org_id, grant.device_id, { grant_id: grantId });
    for (const w of world.wearableAssignments) if (w.device_id === grant.device_id && w.unassigned_at === null) w.unassigned_at = now();
  }

  function alertView(alert: World["alerts"][number]): Alert {
    const classification = world.classifications.find((c) => c.classification_id === alert.classification_id);
    return {
      ...alert, segment_id: classification?.segment_id ?? null, label: classification?.label ?? null,
      confidence: classification?.confidence ?? null,
    };
  }

  function alertsWhere(keep: (patientId: string) => boolean, { unacknowledged = false, limit = 200 }: AlertQuery): Alert[] {
    return world.alerts
      .filter((a) => keep(a.patient_id) && (!unacknowledged || a.acknowledged_at === null))
      .sort((a, b) => b.created_at.localeCompare(a.created_at))
      .slice(0, limit)
      .map(alertView);
  }

  function accountView(user: MockUser): Account {
    const patient = world.patients.find((p) => p.user_id === user.user_id);
    return {
      user_id: user.user_id, zitadel_sub: user.zitadel_sub, role: user.role, status: user.status,
      org_id: user.org_id!, patient_id: patient?.patient_id ?? null, pseudonym: patient?.pseudonym ?? null, created_at: user.created_at,
    };
  }

  function createAccount(orgId: string, role: Role, body: { email: string; given_name: string; family_name: string }, pseudonym?: string | null): NewAccount {
    const org = world.organisations.find((o) => o.org_id === orgId);
    if (!org) throw notFound("organisation");
    if (org.status !== "active") throw conflict("the organisation is suspended");
    if (pseudonym != null && world.patients.some((p) => p.org_id === orgId && p.pseudonym === pseudonym)) {
      throw conflict("pseudonym already used in this organisation");
    }
    if (world.users.some((u) => u.email.toLowerCase() === body.email.toLowerCase())) {
      throw conflict("identity provider: User already exists");
    }
    const user: MockUser = {
      user_id: newId(), zitadel_sub: `z-${newId()}`, role, status: "active", org_id: orgId,
      given_name: body.given_name, family_name: body.family_name, email: body.email, created_at: now(),
    };
    world.users.push(user);
    if (pseudonym != null) world.patients.push({ patient_id: newId(), user_id: user.user_id, org_id: orgId, pseudonym, created_at: now() });
    audit(principal.role === "system_admin" ? "registry" : "organisation", "account.created", orgId, user.user_id, { role });
    // ZITADEL's invite codes are short and single-use; this one only looks like one.
    const invite_code = Array.from({ length: 6 }, () => "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"[Math.floor(Math.random() * 32)]).join("");
    return { ...accountView(user), invite_code };
  }

  /** Sample behaviour of an on-demand recording, worked out when read so it needs no timer: a
   * wearable heard from in the last 15 minutes acks after 3 s and streams for the requested time,
   * then the recording segment appears; one that is quiet never acks, and the command expires after
   * 60 s. The cloud's behaviour is not decided yet (gaps.md). */
  function advanceRecording(request: RecordingRequest) {
    const created = Date.parse(request.created_at);
    const at = Date.now();
    if (request.status === "sent") {
      const wearable = world.devices.find((d) => d.device_id === request.device_id);
      const heard = wearable?.last_seen ? created - Date.parse(wearable.last_seen) < 15 * 60_000 : false;
      if (heard && at >= created + 3_000) Object.assign(request, { status: "acked", acked_at: new Date(created + 3_000).toISOString() });
      else if (!heard && at >= created + 60_000) request.status = "expired";
    }
    if (request.status === "acked" && request.segment_id === null) {
      const start = Date.parse(request.acked_at!) + 1_000;
      if (at >= start + request.duration_s * 1000) {
        const segment_id = newId();
        world.segments.push({
          segment_id, session_id: newId(), patient_id: request.patient_id, device_id: request.device_id, kind: "recording", fs_hz: FS_HZ,
          started_at: new Date(start).toISOString(), ended_at: new Date(start + request.duration_s * 1000).toISOString(),
          signal: { bpm: 70 + Math.floor(Math.random() * 20), ectopicEvery: null, seed: Math.floor(Math.random() * 1e6) },
          attested_by: request.path === "fixed" ? world.devices.find((d) => d.device_id === request.device_id)?.current_gateway_id ?? null : null,
        });
        request.segment_id = segment_id;
        onChange();
      }
    }
    return request;
  }

  function device(deviceId: string) {
    const found = world.devices.find((d) => d.device_id === deviceId);
    if (!found) throw notFound("device");
    return found;
  }

  const TRANSITIONS = { activate: ["pending", "suspended"], suspend: ["active"], revoke: ["pending", "active", "suspended"] } as const;

  function changeDeviceStatus(deviceId: string, action: keyof typeof TRANSITIONS) {
    const d = device(deviceId);
    if (!(TRANSITIONS[action] as readonly string[]).includes(d.status)) throw conflict(`cannot ${action} a ${d.status} device`);
    if (action === "activate" && !world.credentials.some((c) => c.device_id === deviceId && c.status === "active")) {
      throw conflict("a device needs an active credential to be activated");
    }
    if (action === "revoke") {
      for (const c of world.credentials) if (c.device_id === deviceId && c.status === "active") c.status = "revoked";
      const grant = world.grants.find((g) => g.device_id === deviceId && g.revoked_at === null);
      if (grant) closeGrant(grant.grant_id);
    }
    d.status = ({ activate: "active", suspend: "suspended", revoke: "revoked" } as const)[action];
    audit("registry", `device.${d.status}`, null, deviceId);
    return d;
  }

  const newest = (events: AuditEvent[], limit = 200) =>
    [...events].sort((a, b) => b.at.localeCompare(a.at)).slice(0, limit);

  return {
    me: () => answer<Me>(["system_admin", "org_admin", "doctor", "patient"], () => ({ ...principal })),

    organisation: () =>
      answer(["org_admin", "doctor", "patient"], () => {
        const { org_id, name, kind, status, created_at } = world.organisations.find((o) => o.org_id === principal.org_id)!;
        return { org_id, name, kind, status, created_at };
      }),

    directory: () =>
      answer(["org_admin", "doctor", "patient"], () => {
        let visible: MockUser[];
        if (principal.role === "org_admin") {
          visible = world.users.filter((u) => u.org_id === principal.org_id);
        } else if (principal.role === "doctor") {
          const mine = new Set(world.careAssignments.filter((c) => c.doctor_id === principal.user_id && c.valid_to === null).map((c) => c.patient_id));
          const patientUsers = new Set(world.patients.filter((p) => mine.has(p.patient_id)).map((p) => p.user_id));
          visible = world.users.filter((u) => u.user_id === principal.user_id || patientUsers.has(u.user_id));
        } else {
          const doctor = principal.patient_id ? currentDoctor(principal.patient_id) : null;
          visible = world.users.filter((u) => u.user_id === principal.user_id || u.user_id === doctor);
        }
        return visible.map<Person>((u) => ({
          user_id: u.user_id, role: u.role, status: u.status, given_name: u.given_name, family_name: u.family_name,
          email: principal.role === "org_admin" ? u.email : null,
        }));
      }),

    registry: {
      organisations: () => answer(["system_admin"], () => world.organisations),
      createOrganisation: (body) =>
        answer(["system_admin"], () => {
          const org = { org_id: newId(), name: body.name, kind: body.kind, status: "active", zitadel_org_id: `z-${newId()}`, registered_by: principal.user_id, created_at: now() };
          world.organisations.push(org);
          audit("registry", "organisation.created", org.org_id, org.org_id, { name: body.name });
          return org;
        }, true),
      setOrganisationStatus: (orgId, status) =>
        answer(["system_admin"], () => {
          const org = world.organisations.find((o) => o.org_id === orgId);
          if (!org) throw notFound("organisation");
          org.status = status;
          audit("registry", `organisation.${status}`, orgId, orgId);
          return org;
        }, true),
      createOrganisationAdmin: (orgId, body) => answer(["system_admin"], () => createAccount(orgId, "org_admin", body), true),
      devices: () => answer(["system_admin"], () => world.devices),
      device: (deviceId) => answer(["system_admin"], () => device(deviceId)),
      registerDevice: (body) =>
        answer(["system_admin"], () => {
          if (world.devices.some((d) => d.device_id === body.device_id)) {
            throw new ApiError(409, "conflicts with an existing record", { error: "conflicts with an existing record", constraint: "devices_pkey" });
          }
          const d = { device_id: body.device_id, type: body.type, status: "pending" as const, is_testbed: body.is_testbed, current_mode: "unknown", current_gateway_id: null, last_seen: null, registered_by: principal.user_id, created_at: now() };
          world.devices.push(d);
          audit("registry", "device.registered", null, d.device_id, { type: d.type });
          return d;
        }, true),
      activateDevice: (deviceId) => answer(["system_admin"], () => changeDeviceStatus(deviceId, "activate"), true),
      suspendDevice: (deviceId) => answer(["system_admin"], () => changeDeviceStatus(deviceId, "suspend"), true),
      revokeDevice: (deviceId) => answer(["system_admin"], () => changeDeviceStatus(deviceId, "revoke"), true),
      credentials: (deviceId) => answer(["system_admin"], () => world.credentials.filter((c) => c.device_id === deviceId)),
      addCredential: (deviceId, body) =>
        answer(["system_admin"], () => {
          if (device(deviceId).status === "revoked") throw conflict("a revoked device cannot get new credentials");
          let ref = body.credential_ref;
          if (body.auth_method === "x509_mtls") {
            ref = ref.replaceAll(":", "").toUpperCase();
            if (!/^[0-9A-F]{64}$/.test(ref)) throw invalid("an x509_mtls credential_ref is the certificate's SHA-256 fingerprint (64 hex digits)");
          }
          if (world.credentials.some((c) => c.auth_method === body.auth_method && c.credential_ref === ref)) {
            throw new ApiError(409, "conflicts with an existing record", { error: "conflicts with an existing record", constraint: "device_credentials_auth_method_credential_ref_key" });
          }
          const credential = { credential_id: newId(), device_id: deviceId, auth_method: body.auth_method, key_type: body.key_type ?? null, credential_ref: ref, status: "active", created_at: now(), expires_at: body.expires_at ?? null, metadata: body.metadata ?? {} };
          world.credentials.push(credential);
          audit("registry", "credential.added", null, deviceId, { credential_id: credential.credential_id, auth_method: body.auth_method });
          return credential;
        }, true),
      revokeCredential: (credentialId) =>
        answer(["system_admin"], () => {
          const credential = world.credentials.find((c) => c.credential_id === credentialId);
          if (!credential) throw notFound("credential");
          credential.status = "revoked";
          audit("registry", "credential.revoked", null, credential.device_id, { credential_id: credentialId });
          return credential;
        }, true),
      grants: (deviceId) => answer(["system_admin"], () => world.grants.filter((g) => g.device_id === deviceId)),
      grantDevice: (deviceId, orgId) =>
        answer(["system_admin"], () => {
          if (device(deviceId).status === "revoked") throw conflict("a revoked device cannot be granted");
          const org = world.organisations.find((o) => o.org_id === orgId);
          if (!org) throw notFound("organisation");
          if (org.status !== "active") throw conflict("devices can only be granted to an active organisation");
          if (world.grants.some((g) => g.device_id === deviceId && g.revoked_at === null)) {
            throw new ApiError(409, "conflicts with an existing record", { error: "conflicts with an existing record", constraint: "device_grants_one_open" });
          }
          const grant = { grant_id: newId(), device_id: deviceId, org_id: orgId, granted_by: principal.user_id, granted_at: now(), revoked_by: null, revoked_at: null };
          world.grants.push(grant);
          audit("registry", "grant.created", orgId, deviceId, { grant_id: grant.grant_id });
          return grant;
        }, true),
      revokeGrant: (grantId) =>
        answer(["system_admin"], () => {
          const grant = world.grants.find((g) => g.grant_id === grantId);
          if (!grant) throw notFound("grant");
          if (grant.revoked_at !== null) throw conflict("grant already revoked");
          closeGrant(grantId);
          return grant;
        }, true),
      audit: (limit) => answer(["system_admin"], () => newest(world.audit.filter((e) => e.scope === "registry"), limit)),
      securityEvents: (limit = 200) => answer(["system_admin"], () => [...world.securityEvents].sort((a, b) => b.ts.localeCompare(a.ts)).slice(0, limit)),
    },

    attackTests: {
      list: () => answer(["system_admin"], () => [...(world.attackTests ?? [])].sort((a, b) => b.started_at.localeCompare(a.started_at))),
      start: (body) =>
        answer(["system_admin"], () => {
          const target = device(body.target_device_id);
          if (!target.is_testbed) throw conflict("attack tests run only against testbed devices");
          if (target.status === "revoked") throw conflict("the device is revoked");
          world.attackTests ??= [];
          if (world.attackTests.some((t) => t.target_device_id === target.device_id && t.ended_at === null)) {
            throw conflict("an attack test is already running against this device");
          }
          const test: AttackTest = {
            test_id: newId(), target_device_id: target.device_id, triggered_by: principal.user_id, attack_type: body.attack_type,
            parameters: body.params, started_at: now(), ended_at: null,
          };
          world.attackTests.push(test);
          // Sample only: the gateway's IDS "detects" it at once, so the window has an event to correlate.
          const gateway = world.devices.find((d) => d.type === "fixed_gateway" && d.status === "active");
          if (gateway) {
            world.securityEvents.push({
              event_id: newId(), ts: now(), gateway_id: gateway.device_id, device_id: target.device_id, mode: "ids",
              predicted_class: body.attack_type, outcome: "detected", action: null, action_result: null,
            });
          }
          return test;
        }, true),
      stop: (testId) =>
        answer(["system_admin"], () => {
          const test = (world.attackTests ?? []).find((t) => t.test_id === testId);
          if (!test) throw notFound("attack test");
          if (test.ended_at !== null) throw conflict("the attack test has already stopped");
          test.ended_at = now();
          return test;
        }, true),
    },

    org: {
      accounts: () => answer(["org_admin"], () => world.users.filter((u) => u.org_id === principal.org_id).map(accountView)),
      createAccount: (body) =>
        answer(["org_admin"], () => {
          // AccountIn's validator: a pseudonym for a patient, and only for a patient
          if (body.pseudonym === "") throw invalid("pseudonym: String should have at least 1 character");
          if ((body.role === "patient") !== (body.pseudonym != null)) throw invalid("a pseudonym is required for a patient and not allowed otherwise");
          return createAccount(principal.org_id!, body.role, body, body.role === "patient" ? body.pseudonym : null);
        }, true),
      disableAccount: (userId) =>
        answer(["org_admin"], () => {
          const user = world.users.find((u) => u.user_id === userId && u.org_id === principal.org_id);
          if (!user || (user.role !== "doctor" && user.role !== "patient")) throw notFound("account");
          if (user.status === "disabled") throw conflict("account already disabled");
          user.status = "disabled";
          if (user.role === "doctor") {
            for (const c of world.careAssignments) if (c.doctor_id === userId && c.valid_to === null) c.valid_to = now();
          } else {
            const patient = world.patients.find((p) => p.user_id === userId);
            if (patient) endWearableAssignment(patient.patient_id);
          }
          audit("organisation", "account.disabled", principal.org_id, userId);
          return accountView(user);
        }, true),
      assignDoctor: (patientId, doctorId) =>
        answer(["org_admin"], () => {
          const patient = patientInScope(patientId);
          requireActiveAccount(patient);
          if (!world.users.some((u) => u.user_id === doctorId && u.org_id === principal.org_id && u.role === "doctor" && u.status === "active")) {
            throw notFound("doctor");
          }
          const current = world.careAssignments.find((c) => c.patient_id === patientId && c.valid_to === null);
          if (current?.doctor_id === doctorId) return current;
          if (current) current.valid_to = now();
          const assignment = { assignment_id: newId(), patient_id: patientId, doctor_id: doctorId, assigned_by: principal.user_id, valid_from: now(), valid_to: null };
          world.careAssignments.push(assignment);
          audit("organisation", "doctor.assigned", principal.org_id, patientId, { doctor_id: doctorId, previous_doctor_id: current?.doctor_id ?? null });
          return assignment;
        }, true),
      issueWearable: (patientId, deviceId) =>
        answer(["org_admin"], () => {
          const patient = patientInScope(patientId);
          requireActiveAccount(patient);
          const granted = world.grants.some((g) => g.device_id === deviceId && g.org_id === principal.org_id && g.revoked_at === null);
          const d = world.devices.find((x) => x.device_id === deviceId);
          if (!d || !granted) throw notFound("device");
          if (d.type !== "wearable") throw invalid("only a wearable can be issued to a patient");
          if (d.status !== "active") throw conflict(`the wearable is ${d.status}`);
          if (world.wearableAssignments.some((w) => (w.device_id === deviceId || w.patient_id === patientId) && w.unassigned_at === null)) {
            throw new ApiError(409, "conflicts with an existing record", { error: "conflicts with an existing record", constraint: world.wearableAssignments.some((w) => w.device_id === deviceId && w.unassigned_at === null) ? "device_assignments_one_active_per_device" : "device_assignments_one_active_per_patient" });
          }
          const assignment = { device_id: deviceId, patient_id: patientId, issued_by: principal.user_id, assigned_at: now(), unassigned_at: null };
          world.wearableAssignments.push(assignment);
          audit("organisation", "wearable.issued", principal.org_id, patientId, { device_id: deviceId });
          return assignment;
        }, true),
      returnWearable: (patientId) =>
        answer(["org_admin"], () => {
          patientInScope(patientId);
          const ended = endWearableAssignment(patientId);
          if (!ended) throw notFound("wearable assignment");
          audit("organisation", "wearable.returned", principal.org_id, patientId, { device_id: ended.device_id });
          return ended;
        }, true),
      recordDisorder: (patientId, disorder) =>
        answer(["org_admin"], () => {
          patientInScope(patientId);
          if (world.disorders.some((d) => d.patient_id === patientId && d.disorder === disorder)) {
            throw new ApiError(409, "conflicts with an existing record", { error: "conflicts with an existing record", constraint: "patient_disorders_pkey" });
          }
          const row = { patient_id: patientId, disorder, recorded_by: principal.user_id, recorded_at: now() };
          world.disorders.push(row);
          audit("organisation", "disorder.recorded", principal.org_id, patientId, { disorder });
          return row;
        }, true),
      exportPatient: (patientId, destination) =>
        answer(["org_admin"], () => {
          const patient = patientInScope(patientId);
          const export_id = newId();
          world.exports++;
          audit("organisation", "patient.exported", principal.org_id, patientId, { export_id, destination });
          return {
            export_id, exported_by: principal.user_id, destination, created_at: now(),
            patient: { patient_id: patient.patient_id, pseudonym: patient.pseudonym, created_at: patient.created_at },
            disorders: world.disorders.filter((d) => d.patient_id === patientId),
            care_assignments: world.careAssignments.filter((c) => c.patient_id === patientId),
            wearable_assignments: world.wearableAssignments.filter((w) => w.patient_id === patientId),
            ecg_included: false,
          };
        }, true),
      audit: (limit) => answer(["org_admin"], () => newest(world.audit.filter((e) => e.org_id === principal.org_id), limit)),
    },

    patients: () =>
      answer(["org_admin", "doctor"], () =>
        world.patients
          .filter((p) => p.org_id === principal.org_id && (principal.role === "org_admin" || currentDoctor(p.patient_id) === principal.user_id))
          .sort((a, b) => a.pseudonym.localeCompare(b.pseudonym))
          .map<PatientSummary>((p) => ({
            patient_id: p.patient_id, pseudonym: p.pseudonym, user_id: p.user_id, account_status: accountStatus(p),
            doctor_id: currentDoctor(p.patient_id), wearable_id: currentWearable(p.patient_id)?.device_id ?? null, created_at: p.created_at,
          })),
      ),

    disorders: (patientId) =>
      answer(["org_admin", "doctor"], () => {
        patientInScope(patientId);
        return world.disorders.filter((d) => d.patient_id === patientId);
      }),

    devices: () =>
      answer(["org_admin", "doctor"], () => {
        const assignedTo = (deviceId: string) => world.wearableAssignments.find((w) => w.device_id === deviceId && w.unassigned_at === null)?.patient_id ?? null;
        const visible = world.devices.filter((d) => {
          if (principal.role === "org_admin") return world.grants.some((g) => g.device_id === d.device_id && g.org_id === principal.org_id && g.revoked_at === null);
          const patient = assignedTo(d.device_id);
          return patient !== null && world.patients.some((p) => p.patient_id === patient && p.org_id === principal.org_id) && currentDoctor(patient) === principal.user_id;
        });
        return visible
          .sort((a, b) => a.type.localeCompare(b.type) || a.device_id.localeCompare(b.device_id))
          .map((d) => ({ device_id: d.device_id, type: d.type, status: d.status, current_mode: d.current_mode, current_gateway_id: d.current_gateway_id, last_seen: d.last_seen, patient_id: assignedTo(d.device_id) }));
      }),

    recordings: {
      list: (patientId) =>
        answer(["doctor"], () => {
          patientInScope(patientId);
          return (world.recordings ?? [])
            .filter((r) => r.patient_id === patientId)
            .map(advanceRecording)
            .sort((a, b) => b.created_at.localeCompare(a.created_at));
        }),
      request: (patientId, durationS) =>
        answer(["doctor"], () => {
          const patient = patientInScope(patientId);
          if (!Number.isInteger(durationS) || durationS < 10 || durationS > 300) throw invalid("duration_s: between 10 and 300 seconds");
          const assignment = currentWearable(patient.patient_id);
          if (!assignment) throw conflict("the patient has no wearable issued");
          const wearable = world.devices.find((d) => d.device_id === assignment.device_id)!;
          if (wearable.status !== "active") throw conflict(`the wearable is ${wearable.status}`);
          world.recordings ??= [];
          const open = world.recordings.map(advanceRecording).find((r) => r.patient_id === patientId && (r.status === "sent" || (r.status === "acked" && r.segment_id === null)));
          if (open) throw conflict("a recording is already in progress for this patient");
          const request: RecordingRequest = {
            command_id: newId(), patient_id: patientId, device_id: wearable.device_id, issued_by: principal.user_id, type: "ecg_recording",
            path: wearable.current_mode === "mobile" ? "mobile" : "fixed", status: "sent", created_at: now(), acked_at: null, duration_s: durationS, segment_id: null,
          };
          world.recordings.push(request);
          return request;
        }, true),
    },

    care: {
      alerts: (query = {}) =>
        answer(["doctor", "patient"], () => {
          const reachable = (patientId: string) =>
            principal.role === "patient"
              ? patientId === principal.patient_id
              : world.patients.some((p) => p.patient_id === patientId && p.org_id === principal.org_id) && currentDoctor(patientId) === principal.user_id;
          return alertsWhere(reachable, query);
        }),
      patientAlerts: (patientId, query = {}) =>
        answer(["doctor", "patient"], () => {
          patientInScope(patientId);
          return alertsWhere((id) => id === patientId, query);
        }),
      acknowledge: (alertId) =>
        answer(["doctor"], () => {
          const alert = world.alerts.find((a) => a.alert_id === alertId);
          if (!alert) throw notFound("alert");
          patientInScope(alert.patient_id);
          if (alert.acknowledged_at !== null) throw conflict("alert already acknowledged");
          Object.assign(alert, { acknowledged_by: principal.user_id, acknowledged_at: now() });
          return alertView(alert);
        }, true),
      segments: (patientId, limit = 200) =>
        answer(["doctor", "patient"], () => {
          patientInScope(patientId);
          return world.segments
            .filter((s) => s.patient_id === patientId)
            .sort((a, b) => b.started_at.localeCompare(a.started_at))
            .slice(0, limit)
            .map(({ signal: _signal, attested_by: _attested, ...segment }) => segment);
        }),
      segment: (segmentId) =>
        answer(["doctor", "patient"], (): SegmentDetail => {
          const segment = world.segments.find((s) => s.segment_id === segmentId);
          if (!segment) throw notFound("segment");
          try {
            patientInScope(segment.patient_id);
          } catch {
            throw notFound("segment");
          }
          const { signal, attested_by: _attested, ...rest } = segment;
          const seconds = Math.round((Date.parse(segment.ended_at ?? segment.started_at) - Date.parse(segment.started_at)) / 1000);
          const samples = syntheticEcg(seconds, signal.bpm, signal.ectopicEvery, seededRandom(signal.seed));
          const start = Date.parse(segment.started_at);
          return {
            ...rest,
            classifications: world.classifications
              .filter((c) => c.segment_id === segmentId)
              .map(({ segment_id: _segment, ...c }) => c),
            chunks: Array.from({ length: seconds }, (_, seq) => ({
              seq, ts: new Date(start + seq * 1000).toISOString(), n_samples: segment.fs_hz, encoding: "int16le-base64" as const,
              samples: encodeSamples(samples.subarray(seq * segment.fs_hz, (seq + 1) * segment.fs_hz)),
            })),
          };
        }),
    },
  };
}
