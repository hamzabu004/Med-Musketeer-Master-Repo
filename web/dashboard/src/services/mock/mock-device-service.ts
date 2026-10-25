import type { DeviceService } from "@/services/contracts";
import { ServiceError, type Device } from "@/types";
import { mockDelay } from "./mock-delay";
import { mockRepository } from "./mock-repository";
import { assertOwnedByOrganization, findInOrganization, inOrganization } from "./org-scope";

export class MockDeviceService implements DeviceService {
  async list(organizationId: string) {
    await mockDelay();
    return structuredClone(inOrganization(mockRepository.read().devices, organizationId));
  }

  async listForPatients(organizationId: string, patientIds: string[]) {
    await mockDelay();
    return structuredClone(
      mockRepository.read().devices.filter(
        (device) => device.organizationId === organizationId && device.patientId !== null && patientIds.includes(device.patientId),
      ),
    );
  }

  async get(organizationId: string, deviceId: string) {
    await mockDelay();
    return structuredClone(findInOrganization(mockRepository.read().devices, organizationId, deviceId) ?? null);
  }

  async save(organizationId: string, device: Device) {
    await mockDelay();
    if (device.organizationId !== organizationId) {
      throw new ServiceError("VALIDATION", "Wearable device belongs to a different organization.");
    }
    mockRepository.update((data) => {
      if (device.patientId) {
        assertOwnedByOrganization(
          findInOrganization(data.patients, organizationId, device.patientId),
          organizationId,
          "Patient assignment is not valid for this organization.",
        );
      }
      if (device.monitoringStationId) {
        assertOwnedByOrganization(
          findInOrganization(data.monitoringStations, organizationId, device.monitoringStationId),
          organizationId,
          "Monitoring Station assignment is not valid for this organization.",
        );
      }
      const index = data.devices.findIndex((item) => item.id === device.id);
      if (index >= 0 && data.devices[index].organizationId !== organizationId) {
        throw new ServiceError("FORBIDDEN", "Wearable device belongs to a different organization.");
      }
      if (index >= 0) data.devices[index] = structuredClone(device);
      else data.devices.push(structuredClone(device));
    });
    return structuredClone(device);
  }

  async setStatus(organizationId: string, deviceId: string, status: Device["status"]) {
    await mockDelay();
    let result: Device | null = null;
    mockRepository.update((data) => {
      const device = findInOrganization(data.devices, organizationId, deviceId);
      if (device) {
        device.status = status;
        result = structuredClone(device);
      }
    });
    if (!result) throw new ServiceError("NOT_FOUND", "Wearable device not found.");
    return result;
  }

  async assignPatient(organizationId: string, deviceId: string, patientId: string | null) {
    await mockDelay();
    let result: Device | null = null;
    mockRepository.update((data) => {
      const device = findInOrganization(data.devices, organizationId, deviceId);
      if (!device) return;
      if (patientId && !findInOrganization(data.patients, organizationId, patientId)) {
        throw new ServiceError("VALIDATION", "Patient assignment is not valid for this organization.");
      }
      for (const patient of data.patients) {
        if (patient.organizationId !== organizationId) continue;
        if (patient.deviceId === deviceId) {
          patient.deviceId = null;
          patient.monitoringStationId = null;
        }
        if (patient.id === patientId) {
          const previous = data.devices.find((item) => item.organizationId === organizationId && item.id === patient.deviceId);
          if (previous) previous.patientId = null;
          patient.deviceId = deviceId;
          patient.monitoringStationId = device.monitoringStationId;
        }
      }
      device.patientId = patientId;
      for (const station of data.monitoringStations) {
        if (station.organizationId !== organizationId) continue;
        station.patientIds = data.devices
          .filter((item) => item.organizationId === organizationId && item.monitoringStationId === station.id && item.patientId)
          .map((item) => item.patientId as string)
          .filter((id, index, values) => values.indexOf(id) === index);
      }
      result = structuredClone(device);
    });
    if (!result) throw new ServiceError("NOT_FOUND", "Wearable device not found.");
    return result;
  }

  async assignMonitoringStation(organizationId: string, deviceId: string, stationId: string | null) {
    await mockDelay();
    let result: Device | null = null;
    mockRepository.update((data) => {
      const device = findInOrganization(data.devices, organizationId, deviceId);
      if (!device) return;
      if (stationId && !findInOrganization(data.monitoringStations, organizationId, stationId)) {
        throw new ServiceError("VALIDATION", "Monitoring Station assignment is not valid for this organization.");
      }
      for (const station of data.monitoringStations) {
        if (station.organizationId !== organizationId) continue;
        station.deviceIds = station.deviceIds.filter((id) => id !== deviceId);
        if (station.id === stationId) station.deviceIds.push(deviceId);
      }
      device.monitoringStationId = stationId;
      if (device.patientId) {
        const patient = findInOrganization(data.patients, organizationId, device.patientId);
        if (patient) patient.monitoringStationId = stationId;
      }
      for (const station of data.monitoringStations) {
        if (station.organizationId !== organizationId) continue;
        station.patientIds = data.devices
          .filter((item) => item.organizationId === organizationId && item.monitoringStationId === station.id && item.patientId)
          .map((item) => item.patientId as string)
          .filter((id, index, values) => values.indexOf(id) === index);
      }
      result = structuredClone(device);
    });
    if (!result) throw new ServiceError("NOT_FOUND", "Wearable device not found.");
    return result;
  }
}
