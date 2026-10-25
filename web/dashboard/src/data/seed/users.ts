import type { User } from "@/types";

export const users: User[] = [
  { id: "USR-P-001", organizationId: "ORG-001", email: "patient@medmusketeer.demo", role: "patient", displayName: "Ali Khan", status: "active" },
  { id: "USR-D-001", organizationId: "ORG-001", email: "doctor@medmusketeer.demo", role: "doctor", displayName: "Dr. Sarah Ahmed", status: "active" },
  { id: "USR-A-001", organizationId: "ORG-001", email: "admin@medmusketeer.demo", role: "admin", displayName: "Organization Administrator", status: "active" },
  { id: "USR-P-101", organizationId: "ORG-002", email: "patient.org2@medmusketeer.demo", role: "patient", displayName: "Maryam Siddiqui", status: "disabled" },
  { id: "USR-D-101", organizationId: "ORG-002", email: "doctor.org2@medmusketeer.demo", role: "doctor", displayName: "Dr. Omar Malik", status: "disabled" },
  { id: "USR-A-101", organizationId: "ORG-002", email: "admin.org2@medmusketeer.demo", role: "admin", displayName: "Cardiac Organization Admin", status: "disabled" },
];

export const DEMO_PASSWORD = "demo123";
