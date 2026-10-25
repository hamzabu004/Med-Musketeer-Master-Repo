import type { SecurityEvent } from "@/types";

export const securityEvents: SecurityEvent[] = [
  { id: "SEC-001", organizationId: "ORG-001", type: "flooding", timestamp: "2026-09-10T04:12:00+05:00", source: "10.20.4.90", destination: "192.168.20.12", monitoringStationId: "MS-02", severity: "critical", detectionMechanism: "Network anomaly detector", response: "blocked", status: "acknowledged" },
  { id: "SEC-002", organizationId: "ORG-001", type: "auth-failure", timestamp: "2026-09-10T03:57:00+05:00", source: "10.20.4.21", destination: "auth-service", severity: "warning", detectionMechanism: "Authentication threshold rule", response: "logged", status: "resolved" },
  { id: "SEC-003", organizationId: "ORG-001", type: "unknown-device", timestamp: "2026-09-10T04:18:00+05:00", source: "DEV-UNKNOWN-09", destination: "MS-01", monitoringStationId: "MS-01", severity: "critical", detectionMechanism: "Device identity validation", response: "quarantined", status: "active" },
  { id: "SEC-004", organizationId: "ORG-001", type: "suspicious-traffic", timestamp: "2026-09-09T23:40:00+05:00", source: "10.20.4.56", destination: "192.168.20.11", monitoringStationId: "MS-01", severity: "warning", detectionMechanism: "Traffic anomaly detector", response: "logged", status: "resolved" },
  { id: "SEC-101", organizationId: "ORG-002", type: "auth-failure", timestamp: "2026-09-10T04:08:00+05:00", source: "10.30.8.42", destination: "auth-service", severity: "warning", detectionMechanism: "Authentication threshold rule", response: "logged", status: "active" },
];
