/** Sign-in through ZITADEL (D14): authorization code with PKCE, no client secret. The settings come
 * from the API's GET /auth/config, so one build works against any cloud. Tokens live in
 * sessionStorage (this tab only, gone when it closes), never in localStorage. */
import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import { ApiError, errorFromResponse } from "@/api/errors";
import type { AuthConfig } from "@/api/types";
import { apiUrl } from "@/config/capabilities";

export const CALLBACK_PATH = "/auth/callback";

let manager: Promise<UserManager> | null = null;

export function userManager(): Promise<UserManager> {
  manager ??= (async () => {
    const response = await fetch(`${apiUrl.replace(/\/$/, "")}/auth/config`).catch(() => null);
    if (!response) throw new ApiError(0, "the server could not be reached");
    if (!response.ok) throw await errorFromResponse(response);
    const config = (await response.json()) as AuthConfig;
    const store = new WebStorageStateStore({ store: window.sessionStorage });
    return new UserManager({
      authority: config.issuer,
      client_id: config.client_id,
      scope: config.scope,
      redirect_uri: `${window.location.origin}${CALLBACK_PATH}`,
      post_logout_redirect_uri: `${window.location.origin}/`,
      response_type: "code",
      userStore: store,
      stateStore: store,
      // Renew with the refresh token before the access token expires.
      automaticSilentRenew: true,
    });
  })().catch((error: unknown) => {
    manager = null; // a failed attempt (server down, sign-in not configured) is retried next time
    throw error;
  });
  return manager;
}
