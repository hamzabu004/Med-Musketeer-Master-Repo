"use client";

/** Who is signed in, and the data source for them. In API mode the user signs in with ZITADEL and
 * the role comes from the API's /me; in sample-data mode they pick a sample account. */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { ApiError, userMessage } from "@/api/errors";
import { apiUrl, dataSource } from "@/config/capabilities";
import { createApiDataSource } from "@/services/api";
import type { DataSource } from "@/services/contracts";
import { createHttp } from "@/services/http";
import { createMockDataSource, principalOf } from "@/services/mock/mock-data-source";
import { sampleUserId, sampleWorld, saveSampleWorld, signInSample, signOutSample } from "@/services/mock/sample-session";
import { userManager } from "./oidc";
import { ROLES, type Role } from "./roles";

/** The signed-in user, as the API's `/me` describes them. */
export interface Session {
  userId: string;
  role: Role;
  orgId: string | null;
  /** Set for a patient only. */
  patientId: string | null;
}

export type SessionState =
  | { status: "loading" }
  | { status: "signedOut"; message?: string }
  /** Signed in with ZITADEL, but the API does not know the account or refuses its role. */
  | { status: "noAccess"; message: string }
  | { status: "error"; message: string }
  | { status: "signedIn"; session: Session; data: DataSource };

interface SessionContextValue {
  state: SessionState;
  /** API mode: redirects to ZITADEL. Sample mode: signs in as the given sample account. */
  signIn: (sampleUserId?: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Re-reads the session (after the sign-in callback stored the tokens). */
  reload: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

async function sessionFromMe(data: DataSource): Promise<Session> {
  const me = await data.me();
  if (!(ROLES as readonly string[]).includes(me.role)) throw new ApiError(403, `unknown role ${me.role}`);
  return { userId: me.user_id, role: me.role as Role, orgId: me.org_id, patientId: me.patient_id };
}

async function loadSample(): Promise<SessionState> {
  const userId = sampleUserId();
  const world = sampleWorld();
  const user = world.users.find((u) => u.user_id === userId && u.status === "active");
  if (!user) return { status: "signedOut" };
  const data = createMockDataSource(world, principalOf(world, user), saveSampleWorld);
  return { status: "signedIn", session: await sessionFromMe(data), data };
}

/** The access token in use; kept current by the manager's automatic renewal. */
let accessToken: string | null = null;
let following = false;

async function loadApi(): Promise<SessionState> {
  const manager = await userManager();
  if (!following) {
    following = true;
    manager.events.addUserLoaded((user) => {
      accessToken = user.access_token;
    });
    manager.events.addUserUnloaded(() => {
      accessToken = null;
    });
  }
  let user = await manager.getUser();
  if (user?.expired) user = await manager.signinSilent().catch(() => null);
  accessToken = user?.access_token ?? null;
  if (!user) return { status: "signedOut" };

  const http = createHttp({
    baseUrl: apiUrl,
    getToken: () => accessToken,
    refresh: async () => {
      const renewed = await manager.signinSilent().catch(() => null);
      accessToken = renewed?.access_token ?? null;
      return accessToken;
    },
  });
  const data = createApiDataSource(http);
  try {
    return { status: "signedIn", session: await sessionFromMe(data), data };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      await manager.removeUser();
      return { status: "signedOut", message: "Your session has ended. Sign in again." };
    }
    if (error instanceof ApiError && error.status === 403) {
      return {
        status: "noAccess",
        message: "You are signed in, but this account has no access to MedMusketeer. Ask your administrator to check your account.",
      };
    }
    throw error;
  }
}

async function load(): Promise<SessionState> {
  try {
    return await (dataSource === "mock" ? loadSample() : loadApi());
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      return { status: "error", message: "Sign-in is not set up on the server yet: it has no dashboard app (DASHBOARD_ORIGINS)." };
    }
    return { status: "error", message: error instanceof ApiError ? userMessage(error) : "Sign-in is unavailable: the server could not be reached." };
  }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: "loading" });

  const reload = useCallback(async () => setState(await load()), []);

  useEffect(() => {
    let current = true;
    void load().then((loaded) => {
      if (current) setState(loaded);
    });
    return () => {
      current = false;
    };
  }, []);

  const signIn = useCallback(
    async (userId?: string) => {
      if (dataSource === "mock") {
        if (userId) signInSample(userId);
        await reload();
        return;
      }
      await (await userManager()).signinRedirect();
    },
    [reload],
  );

  const signOut = useCallback(async () => {
    if (dataSource === "mock") {
      signOutSample();
      setState({ status: "signedOut" });
      return;
    }
    const manager = await userManager();
    // Ends the ZITADEL session too, then returns to the dashboard's start page.
    await manager.signoutRedirect().catch(async () => {
      await manager.removeUser();
      setState({ status: "signedOut" });
    });
  }, []);

  const value = useMemo(() => ({ state, signIn, signOut, reload }), [state, signIn, signOut, reload]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession outside SessionProvider");
  return value;
}

/** The data source of the signed-in user; for screens inside a RoleArea, which only renders once signed in. */
export function useData(): { session: Session; data: DataSource } {
  const { state } = useSession();
  if (state.status !== "signedIn") throw new Error("useData before sign-in");
  return { session: state.session, data: state.data };
}
