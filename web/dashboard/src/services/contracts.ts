/** What the screens can ask for, one group per cloud resource. Two implementations: the cloud API
 * (services/api.ts) and sample data (services/mock/), which applies the same D9 rules. Every method
 * rejects with an ApiError the way the API answers. */
import type {
  Account,
  AccountIn,
  Alert,
  AuditEvent,
  CareAssignment,
  ConnectivityEvent,
  Credential,
  CredentialIn,
  Device,
  DeviceIn,
  Disorder,
  GatewayAlert,
  GatewayDetail,
  Grant,
  Me,
  NewAccount,
  OrgDevice,
  OrgGateway,
  Organisation,
  OrganisationIn,
  OwnOrganisation,
  PatientExport,
  PatientSummary,
  Person,
  PersonIn,
  RevocationStatus,
  SecurityEvent,
  Segment,
  SegmentDetail,
  WearableAssignment,
} from "@/api/types";

/** An attack test (docs/decisions/stack.md, "Attack-testing"): an attack run against a testbed
 * device, whose window is the ground truth for the IDS/IPS metrics. Not served by the cloud yet. */
export interface AttackTest {
  test_id: string;
  target_device_id: string;
  triggered_by: string;
  attack_type: string;
  parameters: Record<string, unknown>;
  started_at: string;
  ended_at: string | null;
}

export interface AttackTestIn {
  attack_type: string;
  target_device_id: string;
  params: Record<string, unknown>;
}

/** An on-demand ECG recording a doctor requested (stack.md ADR-1): a `commands` row sent to the
 * patient's wearable (sent, acked by the wearable, or expired), and the `recording` segment that
 * references it once the wearable has streamed it. Not served by the cloud yet: how a recording
 * starts and stops is open (gaps.md), so this shape is provisional, modelled on the schema. */
export interface RecordingRequest {
  command_id: string;
  patient_id: string;
  device_id: string;
  issued_by: string;
  type: "ecg_recording";
  path: "fixed" | "mobile";
  status: "sent" | "acked" | "expired";
  created_at: string;
  acked_at: string | null;
  duration_s: number;
  segment_id: string | null;
}

export interface AlertQuery {
  unacknowledged?: boolean;
  limit?: number;
}

export interface DataSource {
  me(): Promise<Me>;
  /** The caller's own organisation (org admin, doctor, patient). */
  organisation(): Promise<OwnOrganisation>;
  /** Names of the people the caller works with (D14). */
  directory(): Promise<Person[]>;

  /** System admin: the registry. */
  registry: {
    organisations(): Promise<Organisation[]>;
    createOrganisation(body: OrganisationIn): Promise<Organisation>;
    setOrganisationStatus(orgId: string, status: "active" | "suspended"): Promise<Organisation>;
    /** Returns the invite code once; it cannot be read again. */
    createOrganisationAdmin(orgId: string, body: PersonIn): Promise<NewAccount>;
    devices(): Promise<Device[]>;
    device(deviceId: string): Promise<Device>;
    registerDevice(body: DeviceIn): Promise<Device>;
    activateDevice(deviceId: string): Promise<Device>;
    suspendDevice(deviceId: string): Promise<Device>;
    revokeDevice(deviceId: string): Promise<Device>;
    credentials(deviceId: string): Promise<Credential[]>;
    addCredential(deviceId: string, body: CredentialIn): Promise<Credential>;
    revokeCredential(credentialId: string): Promise<Credential>;
    grants(deviceId: string): Promise<Grant[]>;
    grantDevice(deviceId: string, orgId: string): Promise<Grant>;
    revokeGrant(grantId: string): Promise<Grant>;
    audit(limit?: number): Promise<AuditEvent[]>;
    securityEvents(limit?: number): Promise<SecurityEvent[]>;
    /** The wearable revocation list (D16): its version, what EMQX holds, and the active gateways
     * that have not reported the published version. */
    revocation(): Promise<RevocationStatus>;
  };

  /** System admin: attack tests (capability "attackTests"). Refused for a production device. */
  attackTests: {
    list(): Promise<AttackTest[]>;
    start(body: AttackTestIn): Promise<AttackTest>;
    stop(testId: string): Promise<AttackTest>;
  };

  /** Org admin: people, patients and devices of the own organisation. */
  org: {
    accounts(): Promise<Account[]>;
    /** Returns the invite code once; it cannot be read again. */
    createAccount(body: AccountIn): Promise<NewAccount>;
    disableAccount(userId: string): Promise<Account>;
    assignDoctor(patientId: string, doctorId: string): Promise<CareAssignment>;
    issueWearable(patientId: string, deviceId: string): Promise<WearableAssignment>;
    returnWearable(patientId: string): Promise<WearableAssignment>;
    recordDisorder(patientId: string, disorder: string): Promise<Disorder>;
    exportPatient(patientId: string, destination: string): Promise<PatientExport>;
    audit(limit?: number): Promise<AuditEvent[]>;
  };

  /** Org admin: the gateways granted to the organisation (D17). Alerts are their times only (D9). */
  gateways: {
    list(): Promise<OrgGateway[]>;
    detail(gatewayId: string): Promise<GatewayDetail>;
    /** The gateway's connections and its wearables' presence through it, newest first. */
    connectivity(gatewayId: string, limit?: number): Promise<ConnectivityEvent[]>;
    alerts(gatewayId: string, limit?: number): Promise<GatewayAlert[]>;
  };

  /** Org admin (whole organisation) and doctor (own patients). */
  patients(): Promise<PatientSummary[]>;
  disorders(patientId: string): Promise<Disorder[]>;
  /** Org admin: devices granted to the organisation; doctor: their patients' wearables. */
  devices(): Promise<OrgDevice[]>;

  /** Doctor (own patients) and patient (self): ECG and alerts. */
  care: {
    alerts(query?: AlertQuery): Promise<Alert[]>;
    patientAlerts(patientId: string, query?: AlertQuery): Promise<Alert[]>;
    acknowledge(alertId: string): Promise<Alert>;
    segments(patientId: string, limit?: number): Promise<Segment[]>;
    segment(segmentId: string): Promise<SegmentDetail>;
  };

  /** Doctor: on-demand recordings of their own patients (capability "ecgRequests"). */
  recordings: {
    list(patientId: string): Promise<RecordingRequest[]>;
    request(patientId: string, durationS: number): Promise<RecordingRequest>;
  };
}
