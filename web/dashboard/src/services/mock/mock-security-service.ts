import type { SecurityService } from "@/services/contracts";
import type { SecurityEvent } from "@/types";
import { mockDelay } from "./mock-delay";
import { mockRepository } from "./mock-repository";
import { findInOrganization, inOrganization } from "./org-scope";

export class MockSecurityService implements SecurityService {
  async listEvents(organizationId: string) {
    await mockDelay();
    return structuredClone(inOrganization(mockRepository.read().securityEvents, organizationId));
  }

  async getEvent(organizationId: string, eventId: string) {
    await mockDelay();
    return structuredClone(findInOrganization(mockRepository.read().securityEvents, organizationId, eventId) ?? null);
  }

  async acknowledge(organizationId: string, eventId: string) {
    await mockDelay();
    let result: SecurityEvent | null = null;
    mockRepository.update((data) => {
      const event = findInOrganization(data.securityEvents, organizationId, eventId);
      if (event) {
        event.status = "acknowledged";
        result = structuredClone(event);
      }
    });
    return result;
  }

  async resolve(organizationId: string, eventId: string) {
    await mockDelay();
    let result: SecurityEvent | null = null;
    mockRepository.update((data) => {
      const event = findInOrganization(data.securityEvents, organizationId, eventId);
      if (event) {
        event.status = "resolved";
        result = structuredClone(event);
      }
    });
    return result;
  }
}
