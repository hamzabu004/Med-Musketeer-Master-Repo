"use client";

/** Who is signed in, and the data source for them. In API mode the user signs in with ZITADEL and
 * the role comes from the API's /me; in sample-data mode they pick a sample account. */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, userMessage } from "@/api/errors";
import { apiUrl, dataSource } from "@/config/capabilities";
import { createApiDataSource } from "@/services/api";
import type { DataSource } from "@/services/contracts";
import { createHttp, singleFlight } from "@/services/http";
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
  try {
    return { status: "signedIn", session: await sessionFromMe(data), data };
  } catch (error) {
    if (error instanceof ApiError && error.status === 403) return noAccess(error);
    throw error;
  }
}

/** The access token in use; kept current by the manager's automatic renewal. */
let accessToken: string | null = null;
let following = false;
/** Set by the provider: moves the state to signed out when the session can no longer be renewed. */
let sessionEnded: () => void = () => {};

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
    manager.events.addSilentRenewError(() => sessionEnded());
  }
  /** One renewal at a time: ZITADEL rotates refresh tokens, so parallel renewals would refuse each other. */
  const renew = singleFlight(async () => {
    const renewed = await manager.signinSilent().catch(() => null);
    accessToken = renewed?.access_token ?? null;
    if (!accessToken) sessionEnded();
    return accessToken;
  });
  let user = await manager.getUser();
  if (user?.expired) user = await manager.signinSilent().catch(() => null);
  accessToken = user?.access_token ?? null;
  if (!user) return { status: "signedOut" };

  const http = createHttp({
    baseUrl: apiUrl,
    getToken: () => accessToken,
    refresh: renew,
  });
  const data = createApiDataSource(http);
  try {
    return { status: "signedIn", session: await sessionFromMe(data), data };
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      await manager.removeUser();
      return { status: "signedOut", message: "Your session has ended. Sign in again." };
    }
    if (error instanceof ApiError && error.status === 403) return noAccess(error);
    throw error;
  }
}

function noAccess(error: ApiError): SessionState {
  return {
    status: "noAccess",
    message:
      error.message === "organisation suspended"
        ? "Your organisation is suspended, so MedMusketeer cannot be used for now. Ask your administrator."
        : "You are signed in, but this account has no access to MedMusketeer. Ask your administrator to check your account.",
  };
}

async function load(): Promise<SessionState> {
  try {
    return await (dataSource === "mock" ? loadSample() : loadApi());
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      // e.g. "authentication is not configured": no ZITADEL config, or no dashboard app (DASHBOARD_ORIGINS)
      return { status: "error", message: `Sign-in is unavailable: the server answered "${error.message}".` };
    }
    return { status: "error", message: userMessage(error) };
  }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: "loading" });

  // Only the latest load may set the state: the first load on /auth/callback runs before the code
  // exchange has stored the tokens, and must not overwrite the reload that follows it.
  const latest = useRef(0);
  const reload = useCallback(async () => {
    const mine = ++latest.current;
    const loaded = await load();
    if (mine === latest.current) setState(loaded);
  }, []);

  useEffect(() => {
    const generation = latest; // a counter, not a DOM node
    const mine = ++generation.current;
    void load().then((loaded) => {
      if (mine === generation.current) setState(loaded);
    });
    sessionEnded = () => {
      generation.current++;
      setState({ status: "signedOut", message: "Your session has ended. Sign in again." });
    };
    return () => {
      generation.current++;
      sessionEnded = () => {};
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
