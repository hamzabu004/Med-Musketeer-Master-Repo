import type { Severity } from "./alerts";

export interface SecurityEvent {
  id: string;
  organizationId: string;
  type: "flooding" | "auth-failure" | "unknown-device" | "suspicious-traffic";
  timestamp: string;
  source: string;
  destination?: string;
  monitoringStationId?: string;
  severity: Severity;
  detectionMechanism: string;
  response: "logged" | "blocked" | "quarantined" | "none";
  status: "active" | "acknowledged" | "resolved";
}
