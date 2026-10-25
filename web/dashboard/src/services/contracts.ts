/** What the screens can ask for, one group per cloud resource. Two implementations: the cloud API
 * (services/api.ts) and sample data (services/mock/), which applies the same D9 rules. Every method
 * rejects with an ApiError the way the API answers. */
import type {
  Account,
  AccountIn,
  Alert,
  AuditEvent,
  CareAssignment,
  Credential,
  CredentialIn,
  Device,
  DeviceIn,
  Disorder,
  Grant,
  Me,
  NewAccount,
  OrgDevice,
  Organisation,
  OrganisationIn,
  OwnOrganisation,
  PatientExport,
  PatientSummary,
  Person,
  PersonIn,
  SecurityEvent,
  Segment,
  SegmentDetail,
  WearableAssignment,
} from "@/api/types";

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
}
