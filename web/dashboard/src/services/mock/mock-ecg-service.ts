import type { ECGService } from "@/services/contracts";
import { ServiceError, type ECGEvent, type ECGRequest } from "@/types";
import { mockDelay } from "./mock-delay";
import { mockRepository } from "./mock-repository";
import { findInOrganization } from "./org-scope";

const activeRequestStatuses = ["queued", "sent-to-device", "acquiring", "uploading"] as const;
const generatedWaveform = [0, 1, 2, 1, 0, -1, 0, 2, 8, 18, 6, -4, -2, 0, 2, 3, 2, 1, 0, 0];

function isActiveRequest(request: ECGRequest) {
  return activeRequestStatuses.some((status) => status === request.status);
}

function advanceRequestQueue(organizationId: string) {
  const now = Date.now();
  mockRepository.update((data) => {
    for (const request of data.ecgRequests.filter((item) => item.organizationId === organizationId)) {
      if (!isActiveRequest(request)) continue;

      const ageSeconds = Math.floor((now - Date.parse(request.createdAt)) / 1000);
      const device = findInOrganization(data.devices, organizationId, request.deviceId);
      const patient = findInOrganization(data.patients, organizationId, request.patientId);
      if (!device || !patient) {
        request.status = "failed";
        request.failureReason = "Patient or device assignment is no longer available.";
        continue;
      }

      if (device.status !== "online" && ageSeconds >= 120) {
        request.status = "expired";
        request.failureReason = "Device did not become available before the request timeout.";
        continue;
      }

      if (device.status !== "online") {
        request.status = "queued";
        continue;
      }

      if (ageSeconds >= 35) {
        request.status = "completed";
        request.acquisitionStartedAt ??= new Date(Date.parse(request.createdAt) + 15000).toISOString();
        request.completedAt = new Date().toISOString();
        if (!request.resultEventId) {
          const eventId = `ECG-${request.id}`;
          const classification = patient.ecgClassification === "abnormal" ? "abnormal" : "normal";
          const event: ECGEvent = {
            id: eventId,
            organizationId,
            patientId: request.patientId,
            requestId: request.id,
            acquisitionReason: request.source === "alert" ? "Alert triggered" : "Doctor requested",
            timestamp: request.completedAt,
            classification,
            heartRate: patient.currentHeartRate,
            durationSeconds: 10,
            deviceId: request.deviceId,
            monitoringStationId: patient.monitoringStationId ?? device.monitoringStationId ?? "Unassigned",
            waveform: generatedWaveform,
            alertStatus: request.source === "alert" ? "open" : "read",
          };
          data.ecgEvents.push(event);
          request.resultEventId = event.id;
          patient.ecgClassification = classification;
          patient.lastUpdatedAt = request.completedAt;
        }
      } else if (ageSeconds >= 24) {
        request.status = "uploading";
        request.acquisitionStartedAt ??= new Date(Date.parse(request.createdAt) + 15000).toISOString();
      } else if (ageSeconds >= 15) {
        request.status = "acquiring";
        request.acquisitionStartedAt ??= new Date().toISOString();
      } else if (ageSeconds >= 6) {
        request.status = "sent-to-device";
      }
    }
  });
}

export class MockECGService implements ECGService {
  async listEventsForPatient(organizationId: string, patientId: string) {
    await mockDelay();
    advanceRequestQueue(organizationId);
    return structuredClone(
      mockRepository.read().ecgEvents.filter((event) => event.organizationId === organizationId && event.patientId === patientId),
    );
  }

  async getEvent(organizationId: string, eventId: string) {
    await mockDelay();
    advanceRequestQueue(organizationId);
    return structuredClone(findInOrganization(mockRepository.read().ecgEvents, organizationId, eventId) ?? null);
  }

  async listHeartRateReadings(organizationId: string, patientId: string) {
    await mockDelay();
    return structuredClone(
      mockRepository.read().heartRateReadings.filter((reading) => reading.organizationId === organizationId && reading.patientId === patientId),
    );
  }

  async listRequestsForPatient(organizationId: string, patientId: string) {
    await mockDelay();
    advanceRequestQueue(organizationId);
    return structuredClone(
      mockRepository.read().ecgRequests.filter((request) => request.organizationId === organizationId && request.patientId === patientId),
    );
  }

  async listRequestsForPatients(organizationId: string, patientIds: string[]) {
    await mockDelay();
    advanceRequestQueue(organizationId);
    const allowed = new Set(patientIds);
    return structuredClone(
      mockRepository.read().ecgRequests.filter((request) => request.organizationId === organizationId && allowed.has(request.patientId)),
    );
  }

  async listPendingRequestsForDevice(organizationId: string, deviceId: string) {
    await mockDelay();
    advanceRequestQueue(organizationId);
    return structuredClone(
      mockRepository
        .read()
        .ecgRequests.filter((request) => request.organizationId === organizationId && request.deviceId === deviceId && isActiveRequest(request)),
    );
  }

  async createAcquisitionRequest(
    organizationId: string,
    patientId: string,
    requestedByUserId: string,
    source: ECGRequest["source"],
    alertId?: string,
  ): Promise<ECGRequest> {
    await mockDelay();
    let created: ECGRequest | null = null;
    mockRepository.update((data) => {
      const patient = findInOrganization(data.patients, organizationId, patientId);
      if (!patient) throw new ServiceError("NOT_FOUND", "Patient is not available in this organization.");
      if (!patient.deviceId) throw new ServiceError("VALIDATION", "Patient does not have an assigned wearable.");
      const device = findInOrganization(data.devices, organizationId, patient.deviceId);
      if (!device) throw new ServiceError("VALIDATION", "Assigned wearable is not available.");
      const requester = findInOrganization(data.users, organizationId, requestedByUserId);
      if (!requester) throw new ServiceError("FORBIDDEN", "Requesting user is not available in this organization.");
      if (requester.role === "doctor") {
        const doctor = data.doctors.find((item) => item.organizationId === organizationId && item.userId === requestedByUserId);
        if (!doctor || !doctor.patientIds.includes(patientId)) {
          throw new ServiceError("FORBIDDEN", "Clinician is not assigned to this patient.");
        }
      }

      const duplicate = data.ecgRequests.find(
        (request) => request.organizationId === organizationId && request.patientId === patientId && isActiveRequest(request),
      );
      if (duplicate) {
        created = structuredClone(duplicate);
        return;
      }

      const sequence = data.ecgRequests.filter((request) => request.organizationId === organizationId).length + 1;
      const request: ECGRequest = {
        id: `ECGR-${String(sequence).padStart(3, "0")}`,
        organizationId,
        patientId,
        deviceId: device.id,
        requestedByUserId,
        source,
        alertId,
        createdAt: new Date().toISOString(),
        status: "queued",
      };
      data.ecgRequests.push(request);
      created = structuredClone(request);
    });

    const result = created as ECGRequest | null;
    if (!result) throw new ServiceError("UNAVAILABLE", "ECG request could not be created.");
    return result;
  }
}
