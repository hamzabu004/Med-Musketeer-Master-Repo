import type { SecurityEvent } from "@/types";

export interface SecurityService {
  listEvents(organizationId: string): Promise<SecurityEvent[]>;
  getEvent(organizationId: string, eventId: string): Promise<SecurityEvent | null>;
  acknowledge(organizationId: string, eventId: string): Promise<SecurityEvent | null>;
  resolve(organizationId: string, eventId: string): Promise<SecurityEvent | null>;
}
