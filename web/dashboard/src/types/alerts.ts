export type Severity = "info" | "warning" | "critical";
export type EventStatus = "new" | "open" | "acknowledged" | "resolved" | "read";

export interface ClinicalAlert {
  id: string;
  organizationId: string;
  patientId: string;
  type: "ecg" | "device" | "monitoring-station" | "monitoring";
  title: string;
  severity: Severity;
  status: EventStatus;
  timestamp: string;
  ecgClassification?: "normal" | "abnormal" | "unclassified";
  heartRate?: number;
  eventId?: string;
}
