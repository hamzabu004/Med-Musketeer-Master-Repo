import type { User } from "@/types";

export interface IdentityService {
  listUsers(organizationId: string): Promise<User[]>;
  getUser(organizationId: string, userId: string): Promise<User | null>;
  saveUser(organizationId: string, user: User): Promise<User>;
}
