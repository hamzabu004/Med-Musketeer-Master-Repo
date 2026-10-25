import type { MonitoringStation } from "@/types";

export const monitoringStations: MonitoringStation[] = [
  { id: "MS-01", organizationId: "ORG-001", name: "Ward A Monitoring Station", status: "online", deviceIds: ["DEV-001", "DEV-002"], assignedDoctorIds: ["DOC-001"], patientIds: ["PAT-001", "PAT-002"], ipAddress: "192.168.20.11", lastSeenAt: "2026-09-10T04:30:00+05:00" },
  { id: "MS-02", organizationId: "ORG-001", name: "Ward B Monitoring Station", status: "degraded", deviceIds: ["DEV-003"], assignedDoctorIds: [], patientIds: ["PAT-003"], ipAddress: "192.168.20.12", lastSeenAt: "2026-09-10T03:50:00+05:00" },
  { id: "MS-03", organizationId: "ORG-001", name: "Lab Monitoring Station", status: "offline", deviceIds: [], assignedDoctorIds: [], patientIds: [], ipAddress: "192.168.20.13", lastSeenAt: "2026-09-09T22:10:00+05:00" },
  { id: "MS-101", organizationId: "ORG-002", name: "Cardiac Care Monitoring Station", status: "online", deviceIds: ["DEV-101"], assignedDoctorIds: ["DOC-101"], patientIds: ["PAT-101"], ipAddress: "192.168.30.11", lastSeenAt: "2026-09-10T04:18:00+05:00" },
];
