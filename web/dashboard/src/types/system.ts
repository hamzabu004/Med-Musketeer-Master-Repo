import type { ClinicalAlert } from "./alerts";
import type { User } from "./auth";
import type { Device, ECGEvent, ECGRequest, HeartRateReading, MonitoringStation } from "./monitoring";
import type { Organization } from "./organization";
import type { Doctor, Patient } from "./patient";
import type { SecurityEvent } from "./security";

export interface SystemPreferences {
  organizationId: string;
  notificationsEnabled: boolean;
  defaultHistoryRange: "24h" | "7d" | "30d";
  heartRateMonitoringIntervalSeconds: 15 | 30 | 60 | 120 | 300;
  idsEnabled: boolean;
  ipsEnabled: boolean;
}

export interface DemoData {
  schemaVersion: 4;
  organizations: Organization[];
  users: User[];
  patients: Patient[];
  doctors: Doctor[];
  devices: Device[];
  monitoringStations: MonitoringStation[];
  clinicalAlerts: ClinicalAlert[];
  ecgEvents: ECGEvent[];
  ecgRequests: ECGRequest[];
  heartRateReadings: HeartRateReading[];
  securityEvents: SecurityEvent[];
  preferences: SystemPreferences[];
}

export type ServiceErrorCode =
  | "NOT_FOUND"
  | "FORBIDDEN"
  | "VALIDATION"
  | "UNAVAILABLE";

export class ServiceError extends Error {
  constructor(
    public readonly code: ServiceErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "ServiceError";
  }
}
