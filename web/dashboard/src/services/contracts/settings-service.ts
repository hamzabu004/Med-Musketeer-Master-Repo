import type { SystemPreferences } from "@/types";

export interface SettingsService {
  get(organizationId: string): Promise<SystemPreferences>;
  save(organizationId: string, preferences: SystemPreferences): Promise<SystemPreferences>;
}
