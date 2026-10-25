import type { MonitoringStationService } from "@/services/contracts";
import { ServiceError, type MonitoringStation } from "@/types";
import { mockDelay } from "./mock-delay";
import { mockRepository } from "./mock-repository";
import { findInOrganization, inOrganization } from "./org-scope";

export class MockMonitoringStationService implements MonitoringStationService {
  async list(organizationId: string) {
    await mockDelay();
    return structuredClone(inOrganization(mockRepository.read().monitoringStations, organizationId));
  }

  async listAssignedToDoctor(organizationId: string, doctorId: string) {
    await mockDelay();
    return structuredClone(
      mockRepository
        .read()
        .monitoringStations.filter(
          (station) => station.organizationId === organizationId && station.assignedDoctorIds.includes(doctorId),
        ),
    );
  }

  async get(organizationId: string, stationId: string) {
    await mockDelay();
    return structuredClone(findInOrganization(mockRepository.read().monitoringStations, organizationId, stationId) ?? null);
  }

  async save(organizationId: string, station: MonitoringStation) {
    await mockDelay();
    if (station.organizationId !== organizationId) {
      throw new ServiceError("VALIDATION", "Monitoring Station belongs to a different organization.");
    }
    mockRepository.update((data) => {
      for (const doctorId of station.assignedDoctorIds) {
        if (!findInOrganization(data.doctors, organizationId, doctorId)) {
          throw new ServiceError("VALIDATION", "Clinician assignment is not valid for this organization.");
        }
      }
      for (const deviceId of station.deviceIds) {
        if (!findInOrganization(data.devices, organizationId, deviceId)) {
          throw new ServiceError("VALIDATION", "Device assignment is not valid for this organization.");
        }
      }
      for (const patientId of station.patientIds) {
        if (!findInOrganization(data.patients, organizationId, patientId)) {
          throw new ServiceError("VALIDATION", "Patient assignment is not valid for this organization.");
        }
      }
      const index = data.monitoringStations.findIndex((item) => item.id === station.id);
      if (index >= 0 && data.monitoringStations[index].organizationId !== organizationId) {
        throw new ServiceError("FORBIDDEN", "Monitoring Station belongs to a different organization.");
      }
      if (index >= 0) data.monitoringStations[index] = structuredClone(station);
      else data.monitoringStations.push(structuredClone(station));
      for (const doctor of data.doctors) {
        if (doctor.organizationId !== organizationId) continue;
        doctor.monitoringStationIds = doctor.monitoringStationIds.filter((id) => id !== station.id);
        if (station.assignedDoctorIds.includes(doctor.id)) doctor.monitoringStationIds.push(station.id);
      }
    });
    return structuredClone(station);
  }

  async setStatus(organizationId: string, stationId: string, status: MonitoringStation["status"]) {
    await mockDelay();
    let result: MonitoringStation | null = null;
    mockRepository.update((data) => {
      const station = findInOrganization(data.monitoringStations, organizationId, stationId);
      if (station) {
        station.status = status;
        result = structuredClone(station);
      }
    });
    if (!result) throw new ServiceError("NOT_FOUND", "Monitoring Station not found.");
    return result;
  }
}
