import type { IdentityService } from "@/services/contracts";
import { ServiceError, type User } from "@/types";
import { mockDelay } from "./mock-delay";
import { mockRepository } from "./mock-repository";
import { findInOrganization, inOrganization } from "./org-scope";

export class MockIdentityService implements IdentityService {
  async listUsers(organizationId: string) {
    await mockDelay();
    return structuredClone(inOrganization(mockRepository.read().users, organizationId));
  }

  async getUser(organizationId: string, userId: string) {
    await mockDelay();
    return structuredClone(findInOrganization(mockRepository.read().users, organizationId, userId) ?? null);
  }

  async saveUser(organizationId: string, user: User) {
    await mockDelay();
    if (user.organizationId !== organizationId) {
      throw new ServiceError("VALIDATION", "User belongs to a different organization.");
    }
    mockRepository.update((data) => {
      const index = data.users.findIndex((item) => item.id === user.id);
      if (index >= 0 && data.users[index].organizationId !== organizationId) {
        throw new ServiceError("FORBIDDEN", "User belongs to a different organization.");
      }
      if (index >= 0) data.users[index] = structuredClone(user);
      else data.users.push(structuredClone(user));
    });
    return structuredClone(user);
  }
}
