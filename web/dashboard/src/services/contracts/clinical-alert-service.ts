import type { ClinicalAlert } from "@/types";

export interface ClinicalAlertService {
  listForPatient(organizationId: string, patientId: string): Promise<ClinicalAlert[]>;
  listForDoctor(organizationId: string, doctorId: string): Promise<ClinicalAlert[]>;
  get(organizationId: string, alertId: string): Promise<ClinicalAlert | null>;
  markRead(organizationId: string, alertId: string): Promise<ClinicalAlert | null>;
  acknowledge(organizationId: string, alertId: string): Promise<ClinicalAlert | null>;
}
