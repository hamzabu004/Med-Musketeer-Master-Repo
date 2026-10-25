import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/errors";
import { createHttp } from "./http";

const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const fail = (status: number, detail: unknown) => new Response(JSON.stringify({ detail }), { status });

describe("http", () => {
  it("send the bearer token, the query and a JSON body", async () => {
    const fetch = vi.fn().mockResolvedValue(ok([]));
    const http = createHttp({ baseUrl: "https://api.example/", getToken: () => "t1", refresh: async () => null, fetch });
    await http("POST", "/alerts", { query: { unacknowledged: true, limit: undefined }, body: { a: 1 } });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("https://api.example/alerts?unacknowledged=true");
    expect(init.headers).toMatchObject({ Authorization: "Bearer t1", "Content-Type": "application/json" });
    expect(init.body).toBe('{"a":1}');
  });

  it("renew the token once on 401 and retry with the new one", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(fail(401, "expired")).mockResolvedValueOnce(ok({ user_id: "u" }));
    const refresh = vi.fn().mockResolvedValue("t2");
    const http = createHttp({ baseUrl: "", getToken: () => "t1", refresh, fetch });
    await expect(http("GET", "/me")).resolves.toEqual({ user_id: "u" });
    expect(refresh).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[1][1].headers.Authorization).toBe("Bearer t2");
  });

  it("give up with the 401 when the token cannot be renewed", async () => {
    const fetch = vi.fn().mockResolvedValue(fail(401, "expired"));
    const http = createHttp({ baseUrl: "", getToken: () => "t1", refresh: async () => null, fetch });
    await expect(http("GET", "/me")).rejects.toMatchObject({ status: 401 });
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("turn no answer into status 0 and an error answer into its detail", async () => {
    const down = createHttp({ baseUrl: "", getToken: () => null, refresh: async () => null, fetch: vi.fn().mockRejectedValue(new TypeError("fetch failed")) });
    await expect(down("GET", "/me")).rejects.toEqual(new ApiError(0, "the server could not be reached"));
    const refused = createHttp({ baseUrl: "", getToken: () => "t", refresh: async () => null, fetch: vi.fn().mockResolvedValue(fail(403, "not allowed for this role")) });
    await expect(refused("GET", "/accounts")).rejects.toMatchObject({ status: 403, message: "not allowed for this role" });
  });
});
