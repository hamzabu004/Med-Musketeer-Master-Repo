import type { Organization } from "@/types";

export interface OrganizationService {
  get(organizationId: string): Promise<Organization | null>;
}
