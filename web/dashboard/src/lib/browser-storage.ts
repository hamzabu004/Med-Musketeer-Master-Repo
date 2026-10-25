import { createSeedData, DEMO_DATA_VERSION } from "@/data/seed";
import type { DemoData, DemoSession, SystemPreferences } from "@/types";

const DATA_KEY = "medmusketeer:poc:data:v4";
const SESSION_KEY = "medmusketeer:poc:session";
const PREFERENCES_KEY = "medmusketeer:poc:preferences:v4";

function canUseStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function parseJson<T>(raw: string | null): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export class BrowserStorage {
  load(): DemoData {
    const seed = createSeedData();
    if (!canUseStorage()) return seed;

    const stored = parseJson<DemoData>(window.localStorage.getItem(DATA_KEY));
    const migrated = this.migrate(stored);
    if (!stored || migrated !== stored) {
      this.save(migrated);
      return structuredClone(migrated);
    }

    const preferences = parseJson<SystemPreferences[]>(
      window.localStorage.getItem(PREFERENCES_KEY),
    );

    return structuredClone({
      ...migrated,
      preferences: Array.isArray(preferences) ? preferences : migrated.preferences,
    });
  }

  save(data: DemoData): void {
    if (!canUseStorage()) return;
    const snapshot = structuredClone(data);
    window.localStorage.setItem(DATA_KEY, JSON.stringify(snapshot));
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(snapshot.preferences));
  }

  reset(): DemoData {
    const seed = createSeedData();
    this.save(seed);
    return structuredClone(seed);
  }

  migrate(stored: DemoData | null): DemoData {
    if (!stored || stored.schemaVersion !== DEMO_DATA_VERSION) {
      return createSeedData();
    }
    return stored;
  }

  getSession(): DemoSession | null {
    if (!canUseStorage()) return null;
    const session = parseJson<DemoSession>(window.localStorage.getItem(SESSION_KEY));
    if (
      !session ||
      typeof session.userId !== "string" ||
      typeof session.createdAt !== "string" ||
      !["patient", "doctor", "admin"].includes(session.role)
    ) {
      return null;
    }

    if (typeof session.organizationId === "string") return session;

    const user = this.load().users.find((item) => item.id === session.userId && item.role === session.role);
    if (!user) return null;

    const migratedSession = { ...session, organizationId: user.organizationId };
    this.setSession(migratedSession);
    return migratedSession;
  }

  setSession(session: DemoSession): void {
    if (!canUseStorage()) return;
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  }

  clearSession(): void {
    if (!canUseStorage()) return;
    window.localStorage.removeItem(SESSION_KEY);
  }
}

export const browserStorage = new BrowserStorage();

export const storageKeys = {
  data: DATA_KEY,
  session: SESSION_KEY,
  preferences: PREFERENCES_KEY,
} as const;
