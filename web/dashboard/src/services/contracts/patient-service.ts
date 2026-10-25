import type { Patient } from "@/types";

export interface PatientService {
  list(organizationId: string): Promise<Patient[]>;
  getPatient(organizationId: string, patientId: string): Promise<Patient | null>;
  getPatientByUserId(organizationId: string, userId: string): Promise<Patient | null>;
  getAssignedPatients(organizationId: string, doctorId: string): Promise<Patient[]>;
}
