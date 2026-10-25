export type MonitoringState = "normal" | "attention" | "offline" | "unknown";
export type ECGClassification = "normal" | "abnormal" | "unclassified";

export interface Device {
  id: string;
  organizationId: string;
  type: "ecg-wearable";
  patientId: string | null;
  monitoringStationId: string | null;
  status: "online" | "offline" | "disabled" | "pending";
  batteryPercent?: number;
  firmwareVersion?: string;
  identity?: string;
  lastSeenAt?: string;
}

export interface MonitoringStation {
  id: string;
  organizationId: string;
  name: string;
  status: "online" | "degraded" | "offline" | "disabled";
  deviceIds: string[];
  assignedDoctorIds: string[];
  patientIds: string[];
  ipAddress?: string;
  lastSeenAt?: string;
}

export interface ECGEvent {
  id: string;
  organizationId: string;
  patientId: string;
  requestId?: string;
  acquisitionReason?: "Doctor requested" | "Alert triggered";
  timestamp: string;
  classification: ECGClassification;
  heartRate: number | null;
  durationSeconds?: number;
  confidence?: number;
  deviceId: string;
  monitoringStationId: string;
  waveform: number[];
  alertStatus: "new" | "open" | "acknowledged" | "resolved" | "read";
}

export interface HeartRateReading {
  organizationId: string;
  patientId: string;
  timestamp: string;
  bpm: number;
}

export type ECGRequestStatus =
  | "queued"
  | "sent-to-device"
  | "acquiring"
  | "uploading"
  | "completed"
  | "failed"
  | "expired";

export type ECGRequestSource = "doctor" | "alert";

export interface ECGRequest {
  id: string;
  organizationId: string;
  patientId: string;
  deviceId: string;
  requestedByUserId: string;
  source: ECGRequestSource;
  alertId?: string;
  createdAt: string;
  status: ECGRequestStatus;
  acquisitionStartedAt?: string;
  completedAt?: string;
  failureReason?: string;
  resultEventId?: string;
}
