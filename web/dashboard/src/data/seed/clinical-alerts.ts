import type { ClinicalAlert } from "@/types";

export const clinicalAlerts: ClinicalAlert[] = [
  { id: "ALT-001", organizationId: "ORG-001", patientId: "PAT-002", type: "ecg", title: "Abnormal ECG event detected", severity: "critical", status: "new", timestamp: "2026-09-10T04:26:00+05:00", ecgClassification: "abnormal", heartRate: 118, eventId: "ECG-002" },
  { id: "ALT-002", organizationId: "ORG-001", patientId: "PAT-003", type: "device", title: "Wearable device offline", severity: "warning", status: "open", timestamp: "2026-09-10T03:44:00+05:00" },
  { id: "ALT-003", organizationId: "ORG-001", patientId: "PAT-001", type: "monitoring", title: "Monitoring session updated", severity: "info", status: "read", timestamp: "2026-09-10T02:55:00+05:00" },
  { id: "ALT-101", organizationId: "ORG-002", patientId: "PAT-101", type: "monitoring", title: "Monitoring session updated", severity: "info", status: "read", timestamp: "2026-09-10T04:15:00+05:00" },
];
