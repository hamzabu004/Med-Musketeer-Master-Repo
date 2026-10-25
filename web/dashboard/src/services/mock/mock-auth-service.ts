import type { AuthService } from "@/services/contracts";
import { ServiceError, type DemoSession } from "@/types";
import { DEMO_PASSWORD, organizations, users } from "@/data/seed";
import { browserStorage } from "@/lib/browser-storage";
import { mockDelay } from "./mock-delay";

export class MockAuthService implements AuthService {
  async login(email: string, password: string): Promise<DemoSession> {
    await mockDelay();
    const user = users.find((item) => item.email.toLowerCase() === email.trim().toLowerCase());

    if (!user || user.status !== "active" || password !== DEMO_PASSWORD) {
      throw new ServiceError("VALIDATION", "Invalid credentials");
    }
    const organization = organizations.find((item) => item.id === user.organizationId);
    if (!organization || organization.status !== "active") {
      throw new ServiceError("FORBIDDEN", "Organization is not active.");
    }

    const session: DemoSession = {
      userId: user.id,
      role: user.role,
      organizationId: user.organizationId,
      createdAt: new Date().toISOString(),
    };

    browserStorage.setSession(session);
    return session;
  }

  async logout(): Promise<void> {
    browserStorage.clearSession();
  }

  getSession(): DemoSession | null {
    return browserStorage.getSession();
  }
}
