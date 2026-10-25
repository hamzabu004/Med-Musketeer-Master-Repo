import type { DoctorService } from "@/services/contracts";
import { mockDelay } from "./mock-delay";
import { mockRepository } from "./mock-repository";
import { findInOrganization, inOrganization } from "./org-scope";

export class MockDoctorService implements DoctorService {
  async list(organizationId: string) {
    await mockDelay();
    return structuredClone(inOrganization(mockRepository.read().doctors, organizationId));
  }

  async get(organizationId: string, doctorId: string) {
    await mockDelay();
    return structuredClone(findInOrganization(mockRepository.read().doctors, organizationId, doctorId) ?? null);
  }

  async getByUserId(organizationId: string, userId: string) {
    await mockDelay();
    return structuredClone(
      mockRepository.read().doctors.find((doctor) => doctor.organizationId === organizationId && doctor.userId === userId) ?? null,
    );
  }
}
