import type { ClinicalAlertService } from "@/services/contracts";
import type { ClinicalAlert } from "@/types";
import { mockDelay } from "./mock-delay";
import { mockRepository } from "./mock-repository";
import { findInOrganization } from "./org-scope";

function updateStatus(organizationId: string, alertId: string, status: ClinicalAlert["status"]): ClinicalAlert | null {
  let result: ClinicalAlert | null = null;
  mockRepository.update((data) => {
    const alert = findInOrganization(data.clinicalAlerts, organizationId, alertId);
    if (alert) {
      alert.status = status;
      const event = alert.eventId
        ? findInOrganization(data.ecgEvents, organizationId, alert.eventId)
        : undefined;
      if (event) event.alertStatus = status;
      result = structuredClone(alert);
    }
  });
  return result;
}

export class MockClinicalAlertService implements ClinicalAlertService {
  async listForPatient(organizationId: string, patientId: string) {
    await mockDelay();
    return structuredClone(
      mockRepository
        .read()
        .clinicalAlerts.filter((alert) => alert.organizationId === organizationId && alert.patientId === patientId),
    );
  }

  async listForDoctor(organizationId: string, doctorId: string) {
    await mockDelay();
    const data = mockRepository.read();
    const doctor = findInOrganization(data.doctors, organizationId, doctorId);
    if (!doctor) return [];
    return structuredClone(
      data.clinicalAlerts.filter(
        (alert) => alert.organizationId === organizationId && doctor.patientIds.includes(alert.patientId),
      ),
    );
  }

  async get(organizationId: string, alertId: string) {
    await mockDelay();
    return structuredClone(findInOrganization(mockRepository.read().clinicalAlerts, organizationId, alertId) ?? null);
  }

  async markRead(organizationId: string, alertId: string) {
    await mockDelay();
    return updateStatus(organizationId, alertId, "read");
  }

  async acknowledge(organizationId: string, alertId: string) {
    await mockDelay();
    return updateStatus(organizationId, alertId, "acknowledged");
  }
}
