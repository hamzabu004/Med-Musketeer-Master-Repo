import { ApiError, errorFromResponse } from "@/api/errors";

export interface HttpOptions {
  baseUrl: string;
  /** The current access token, or null when signed out. */
  getToken: () => string | null;
  /** Renews the access token (refresh token); returns the new one, or null if that failed. */
  refresh: () => Promise<string | null>;
  fetch?: typeof fetch;
}

export interface RequestOptions {
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
}

/** Runs `fn` once for all callers that ask while it is running, and again for later callers. */
export function singleFlight<T>(fn: () => Promise<T>): () => Promise<T> {
  let running: Promise<T> | null = null;
  return () => {
    running ??= fn().finally(() => {
      running = null;
    });
    return running;
  };
}

export type Http = <T>(method: string, path: string, options?: RequestOptions) => Promise<T>;

/** JSON over fetch with the bearer token. A 401 renews the token once and retries; any other
 * error answer becomes an ApiError, and no answer at all an ApiError with status 0. */
export function createHttp({ baseUrl, getToken, refresh, fetch: fetcher = fetch }: HttpOptions): Http {
  const root = baseUrl.replace(/\/$/, "");

  async function send(method: string, url: string, token: string | null, body: unknown): Promise<Response> {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    try {
      return await fetcher(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch {
      throw new ApiError(0, "the server could not be reached");
    }
  }

  return async function request<T>(method: string, path: string, { query, body }: RequestOptions = {}): Promise<T> {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value !== undefined) search.set(key, String(value));
    }
    const url = `${root}${path}${search.size ? `?${search}` : ""}`;

    let response = await send(method, url, getToken(), body);
    if (response.status === 401) {
      const renewed = await refresh();
      if (renewed) response = await send(method, url, renewed, body);
    }
    if (!response.ok) throw await errorFromResponse(response);
    return (response.status === 204 ? undefined : await response.json()) as T;
  };
}
