import type { Role } from "./roles";

/** The signed-in user, as the API's `/me` describes them. */
export interface Session {
  userId: string;
  role: Role;
  orgId: string | null;
  /** Set for a patient only. */
  patientId: string | null;
}

/** The current session, or null when nobody is signed in. Sign-in (OIDC with ZITADEL) arrives with
 * the data layer; until then nobody is signed in and every area redirects to the sign-in page. */
export function getSession(): Session | null {
  return null;
}

export async function signOut(): Promise<void> {}
