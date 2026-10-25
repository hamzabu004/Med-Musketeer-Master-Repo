import type { Device } from "@/types";

export interface DeviceService {
  list(organizationId: string): Promise<Device[]>;
  listForPatients(organizationId: string, patientIds: string[]): Promise<Device[]>;
  get(organizationId: string, deviceId: string): Promise<Device | null>;
  save(organizationId: string, device: Device): Promise<Device>;
  setStatus(organizationId: string, deviceId: string, status: Device["status"]): Promise<Device>;
  assignPatient(organizationId: string, deviceId: string, patientId: string | null): Promise<Device>;
  assignMonitoringStation(organizationId: string, deviceId: string, stationId: string | null): Promise<Device>;
}
