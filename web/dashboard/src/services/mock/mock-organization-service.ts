import type { OrganizationService } from "@/services/contracts";
import { mockDelay } from "./mock-delay";
import { mockRepository } from "./mock-repository";

export class MockOrganizationService implements OrganizationService {
  async get(organizationId: string) {
    await mockDelay();
    return structuredClone(
      mockRepository.read().organizations.find((organization) => organization.id === organizationId) ?? null,
    );
  }
}
