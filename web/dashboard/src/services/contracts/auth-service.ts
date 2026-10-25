import type { DemoSession } from "@/types";

export interface AuthService {
  login(email: string, password: string): Promise<DemoSession>;
  logout(): Promise<void>;
  getSession(): DemoSession | null;
}
