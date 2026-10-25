import type { MonitoringStation } from "@/types";

export interface MonitoringStationService {
  list(organizationId: string): Promise<MonitoringStation[]>;
  listAssignedToDoctor(organizationId: string, doctorId: string): Promise<MonitoringStation[]>;
  get(organizationId: string, stationId: string): Promise<MonitoringStation | null>;
  save(organizationId: string, station: MonitoringStation): Promise<MonitoringStation>;
  setStatus(organizationId: string, stationId: string, status: MonitoringStation["status"]): Promise<MonitoringStation>;
}
