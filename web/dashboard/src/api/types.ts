/** Domain types: aliases of the cloud API's schemas (src/api/schema.d.ts, generated). */
import type { components } from "./schema";

type Schemas = components["schemas"];

export type Account = Schemas["Account"];
export type AccountIn = Schemas["AccountIn"];
export type NewAccount = Schemas["NewAccount"];
export type Alert = Schemas["Alert"];
export type AuditEvent = Schemas["AuditEvent"];
export type CareAssignment = Schemas["CareAssignment"];
export type ConnectedWearable = Schemas["ConnectedWearable"];
export type Connectivity = Schemas["Connectivity"];
export type ConnectivityEvent = Schemas["ConnectivityEvent"];
export type Chunk = Schemas["Chunk"];
export type Classification = Schemas["Classification"];
export type Credential = Schemas["Credential"];
export type CredentialIn = Schemas["CredentialIn"];
export type Device = Schemas["Device"];
export type DeviceIn = Schemas["DeviceIn"];
export type Disorder = Schemas["Disorder"];
export type GatewayAlert = Schemas["GatewayAlert"];
export type GatewayDetail = Schemas["GatewayDetail"];
export type Grant = Schemas["Grant"];
export type OrgDevice = Schemas["OrgDevice"];
export type OrgGateway = Schemas["OrgGateway"];
export type Organisation = Schemas["Organisation"];
export type OrganisationIn = Schemas["OrganisationIn"];
export type OwnOrganisation = Schemas["OwnOrganisation"];
export type PatientExport = Schemas["PatientExport"];
export type PatientSummary = Schemas["PatientSummary"];
export type Person = Schemas["Person"];
export type PersonIn = Schemas["PersonIn"];
export type RevocationStatus = Schemas["RevocationStatus"];
export type SecurityEvent = Schemas["SecurityEvent"];
export type Segment = Schemas["Segment"];
export type SegmentDetail = Schemas["SegmentDetail"];
export type WearableAssignment = Schemas["WearableAssignment"];

// `/me` and `/auth/config` return plain objects, so the schema has no model for them.

/** GET /me */
export interface Me {
  user_id: string;
  role: string;
  org_id: string | null;
  patient_id: string | null;
}

/** GET /auth/config: the dashboard's sign-in settings (D14). */
export interface AuthConfig {
  issuer: string;
  client_id: string;
  project_id: string;
  scope: string;
}
