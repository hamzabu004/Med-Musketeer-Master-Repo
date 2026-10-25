import type { Device } from "@/types";

export const devices: Device[] = [
  { id: "DEV-001", organizationId: "ORG-001", type: "ecg-wearable", patientId: "PAT-001", monitoringStationId: "MS-01", status: "online", batteryPercent: 82, firmwareVersion: "0.8.2", identity: "mm-dev-001", lastSeenAt: "2026-09-10T04:30:00+05:00" },
  { id: "DEV-002", organizationId: "ORG-001", type: "ecg-wearable", patientId: "PAT-002", monitoringStationId: "MS-01", status: "online", batteryPercent: 61, firmwareVersion: "0.8.2", identity: "mm-dev-002", lastSeenAt: "2026-09-10T04:28:00+05:00" },
  { id: "DEV-003", organizationId: "ORG-001", type: "ecg-wearable", patientId: "PAT-003", monitoringStationId: "MS-02", status: "offline", batteryPercent: 24, firmwareVersion: "0.8.1", identity: "mm-dev-003", lastSeenAt: "2026-09-10T03:42:00+05:00" },
  { id: "DEV-101", organizationId: "ORG-002", type: "ecg-wearable", patientId: "PAT-101", monitoringStationId: "MS-101", status: "online", batteryPercent: 76, firmwareVersion: "0.8.2", identity: "mm-org2-dev-101", lastSeenAt: "2026-09-10T04:18:00+05:00" },
];
