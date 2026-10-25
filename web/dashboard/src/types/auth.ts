export type Role = "patient" | "doctor" | "admin";

export interface User {
  id: string;
  organizationId: string;
  email: string;
  role: Role;
  displayName: string;
  status: "active" | "disabled";
}

export interface DemoSession {
  userId: string;
  role: Role;
  organizationId: string;
  createdAt: string;
}

export type PermissionAction =
  | "view-own-clinical-data"
  | "view-assigned-clinical-data"
  | "acknowledge-clinical-alert"
  | "manage-devices"
  | "manage-monitoring-stations"
  | "manage-identities"
  | "manage-security-events"
  | "manage-system-settings";
