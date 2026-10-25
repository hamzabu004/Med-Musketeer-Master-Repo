import type { ECGEvent, ECGRequest, HeartRateReading } from "@/types";

const normalWaveform = [0,1,2,1,0,-1,0,2,8,18,6,-4,-2,0,2,3,2,1,0,0];
const abnormalWaveform = [0,2,1,-1,0,4,13,6,-7,-2,1,0,5,2,-4,9,18,3,-8,0];

export const ecgEvents: ECGEvent[] = [
  { id: "ECG-001", organizationId: "ORG-001", patientId: "PAT-001", timestamp: "2026-09-10T02:51:00+05:00", classification: "normal", heartRate: 74, durationSeconds: 10, deviceId: "DEV-001", monitoringStationId: "MS-01", waveform: normalWaveform, alertStatus: "read" },
  { id: "ECG-002", organizationId: "ORG-001", patientId: "PAT-002", requestId: "ECGR-001", acquisitionReason: "Alert triggered", timestamp: "2026-09-10T04:26:00+05:00", classification: "abnormal", heartRate: 118, durationSeconds: 12, confidence: 0.91, deviceId: "DEV-002", monitoringStationId: "MS-01", waveform: abnormalWaveform, alertStatus: "new" },
  { id: "ECG-101", organizationId: "ORG-002", patientId: "PAT-101", timestamp: "2026-09-10T04:15:00+05:00", classification: "normal", heartRate: 68, durationSeconds: 10, deviceId: "DEV-101", monitoringStationId: "MS-101", waveform: normalWaveform, alertStatus: "read" },
];

export const ecgRequests: ECGRequest[] = [
  {
    id: "ECGR-001",
    organizationId: "ORG-001",
    patientId: "PAT-002",
    deviceId: "DEV-002",
    requestedByUserId: "USR-D-001",
    source: "alert",
    alertId: "ALT-001",
    createdAt: "2026-09-10T04:25:30+05:00",
    status: "completed",
    acquisitionStartedAt: "2026-09-10T04:25:45+05:00",
    completedAt: "2026-09-10T04:26:00+05:00",
    resultEventId: "ECG-002",
  },
];

export const heartRateReadings: HeartRateReading[] = [
  { organizationId: "ORG-001", patientId: "PAT-001", timestamp: "2026-09-10T01:30:00+05:00", bpm: 71 },
  { organizationId: "ORG-001", patientId: "PAT-001", timestamp: "2026-09-10T02:30:00+05:00", bpm: 73 },
  { organizationId: "ORG-001", patientId: "PAT-001", timestamp: "2026-09-10T03:30:00+05:00", bpm: 72 },
  { organizationId: "ORG-001", patientId: "PAT-001", timestamp: "2026-09-10T04:30:00+05:00", bpm: 74 },
  { organizationId: "ORG-001", patientId: "PAT-002", timestamp: "2026-09-10T03:26:00+05:00", bpm: 84 },
  { organizationId: "ORG-001", patientId: "PAT-002", timestamp: "2026-09-10T04:26:00+05:00", bpm: 118 },
  { organizationId: "ORG-002", patientId: "PAT-101", timestamp: "2026-09-10T03:15:00+05:00", bpm: 67 },
  { organizationId: "ORG-002", patientId: "PAT-101", timestamp: "2026-09-10T04:15:00+05:00", bpm: 68 },
];
