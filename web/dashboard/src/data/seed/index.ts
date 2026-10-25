export * from "./organizations";
export * from "./users";
export * from "./patients";
export * from "./devices";
export * from "./monitoring-stations";
export * from "./clinical-alerts";
export * from "./ecg-events";
export * from "./security-events";

import type { DemoData } from "@/types";
import { clinicalAlerts } from "./clinical-alerts";
import { devices } from "./devices";
import { ecgEvents, ecgRequests, heartRateReadings } from "./ecg-events";
import { monitoringStations } from "./monitoring-stations";
import { organizations } from "./organizations";
import { doctors, patients } from "./patients";
import { securityEvents } from "./security-events";
import { users } from "./users";

export const DEMO_DATA_VERSION = 4 as const;

export function createSeedData(): DemoData {
  return structuredClone({
    schemaVersion: DEMO_DATA_VERSION,
    organizations,
    users,
    patients,
    doctors,
    devices,
    monitoringStations,
    clinicalAlerts,
    ecgEvents,
    ecgRequests,
    heartRateReadings,
    securityEvents,
    preferences: [
      {
        organizationId: "ORG-001",
        notificationsEnabled: true,
        defaultHistoryRange: "24h",
        heartRateMonitoringIntervalSeconds: 60,
        idsEnabled: true,
        ipsEnabled: true,
      },
      {
        organizationId: "ORG-002",
        notificationsEnabled: true,
        defaultHistoryRange: "7d",
        heartRateMonitoringIntervalSeconds: 60,
        idsEnabled: true,
        ipsEnabled: false,
      },
    ],
  });
}
