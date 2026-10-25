import type { DemoStateService } from "@/services/contracts";
import { mockDelay } from "./mock-delay";
import { mockRepository } from "./mock-repository";

export class MockDemoStateService implements DemoStateService {
  async resetDemoData() {
    await mockDelay();
    return mockRepository.reset();
  }
}
