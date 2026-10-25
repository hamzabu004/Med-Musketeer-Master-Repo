import type { PatientService } from "@/services/contracts";
import type { Patient } from "@/types";
import { mockDelay } from "./mock-delay";
import { mockRepository } from "./mock-repository";
import { findInOrganization, inOrganization } from "./org-scope";

export class MockPatientService implements PatientService {
  async list(organizationId: string): Promise<Patient[]> {
    await mockDelay();
    return structuredClone(inOrganization(mockRepository.read().patients, organizationId));
  }

  async getPatient(organizationId: string, patientId: string): Promise<Patient | null> {
    await mockDelay();
    return structuredClone(findInOrganization(mockRepository.read().patients, organizationId, patientId) ?? null);
  }

  async getPatientByUserId(organizationId: string, userId: string): Promise<Patient | null> {
    await mockDelay();
    return structuredClone(
      mockRepository.read().patients.find((patient) => patient.organizationId === organizationId && patient.userId === userId) ?? null,
    );
  }

  async getAssignedPatients(organizationId: string, doctorId: string): Promise<Patient[]> {
    await mockDelay();
    const data = mockRepository.read();
    const doctor = findInOrganization(data.doctors, organizationId, doctorId);
    if (!doctor) return [];
    return structuredClone(
      data.patients.filter((patient) => patient.organizationId === organizationId && doctor.patientIds.includes(patient.id)),
    );
  }
}
