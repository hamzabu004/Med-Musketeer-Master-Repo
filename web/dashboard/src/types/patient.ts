import type { ECGClassification, MonitoringState } from "./monitoring";

export interface Patient {
  id: string;
  organizationId: string;
  userId: string;
  displayName: string;
  assignedDoctorIds: string[];
  deviceId: string | null;
  monitoringStationId: string | null;
  currentHeartRate: number | null;
  ecgClassification: ECGClassification;
  monitoringState: MonitoringState;
  lastUpdatedAt: string;
}

export interface Doctor {
  id: string;
  organizationId: string;
  userId: string;
  displayName: string;
  patientIds: string[];
  monitoringStationIds: string[];
}
