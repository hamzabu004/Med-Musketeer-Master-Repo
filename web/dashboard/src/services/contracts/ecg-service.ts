import type { ECGEvent, ECGRequest, HeartRateReading } from "@/types";

export interface ECGService {
  listEventsForPatient(organizationId: string, patientId: string): Promise<ECGEvent[]>;
  getEvent(organizationId: string, eventId: string): Promise<ECGEvent | null>;
  listHeartRateReadings(organizationId: string, patientId: string): Promise<HeartRateReading[]>;
  listRequestsForPatient(organizationId: string, patientId: string): Promise<ECGRequest[]>;
  listRequestsForPatients(organizationId: string, patientIds: string[]): Promise<ECGRequest[]>;
  listPendingRequestsForDevice(organizationId: string, deviceId: string): Promise<ECGRequest[]>;
  createAcquisitionRequest(
    organizationId: string,
    patientId: string,
    requestedByUserId: string,
    source: ECGRequest["source"],
    alertId?: string,
  ): Promise<ECGRequest>;
}
