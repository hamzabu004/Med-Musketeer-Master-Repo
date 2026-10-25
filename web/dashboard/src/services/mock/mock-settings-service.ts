import type { SettingsService } from "@/services/contracts";
import { ServiceError, type SystemPreferences } from "@/types";
import { mockDelay } from "./mock-delay";
import { mockRepository } from "./mock-repository";

export class MockSettingsService implements SettingsService {
  async get(organizationId: string) {
    await mockDelay();
    const preferences = mockRepository.read().preferences.find((item) => item.organizationId === organizationId);
    if (!preferences) throw new ServiceError("NOT_FOUND", "Organization settings not found.");
    return structuredClone(preferences);
  }

  async save(organizationId: string, preferences: SystemPreferences) {
    await mockDelay();
    if (preferences.organizationId !== organizationId) {
      throw new ServiceError("VALIDATION", "Settings belong to a different organization.");
    }
    if (![15, 30, 60, 120, 300].includes(preferences.heartRateMonitoringIntervalSeconds)) {
      throw new ServiceError("VALIDATION", "Heart-rate monitoring interval is not supported.");
    }
    mockRepository.update((data) => {
      const index = data.preferences.findIndex((item) => item.organizationId === organizationId);
      if (index >= 0) data.preferences[index] = structuredClone(preferences);
      else data.preferences.push(structuredClone(preferences));
    });
    return structuredClone(preferences);
  }
}
