import type { Doctor } from "@/types";

export interface DoctorService {
  list(organizationId: string): Promise<Doctor[]>;
  get(organizationId: string, doctorId: string): Promise<Doctor | null>;
  getByUserId(organizationId: string, userId: string): Promise<Doctor | null>;
}
