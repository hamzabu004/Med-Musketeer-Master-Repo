import { describe, expect, it } from "vitest";
import openapi from "@/api/openapi.json";
import { createApiDataSource } from "./api";
import type { Http } from "./http";

/** Every method of the API data source calls a path and method the cloud's OpenAPI document has. */
describe("API data source", () => {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const http: Http = async (method, path, options) => {
    calls.push({ method, path, body: options?.body });
    return undefined as never;
  };
  const source = createApiDataSource(http);
  const ID = "00000000-0000-4000-8000-000000000001";

  type Method = (...args: unknown[]) => Promise<unknown>;
  const methods: [string, Method][] = [];
  for (const [name, value] of Object.entries(source)) {
    if (typeof value === "function") methods.push([name, value as Method]);
    else for (const [inner, fn] of Object.entries(value as Record<string, Method>)) methods.push([`${name}.${inner}`, fn]);
  }

  const served = methods.filter(([name]) => !name.startsWith("attackTests.") && !name.startsWith("recordings."));

  it.each(served)("%s matches an endpoint", async (_name, fn) => {
    calls.length = 0;
    await fn(ID, ID);
    const [{ method, path }] = calls;
    const template = path.replaceAll(ID, "{id}");
    const known = Object.entries(openapi.paths as Record<string, Record<string, unknown>>).some(
      ([documented, operations]) => documented.replace(/\{[^}]+\}/g, "{id}") === template && method.toLowerCase() in operations,
    );
    expect(known, `${method} ${path}`).toBe(true);
  });

  it("refuses what the cloud does not serve yet, without calling it", async () => {
    calls.length = 0;
    await expect(source.attackTests.list()).rejects.toMatchObject({ status: 501 });
    await expect(source.recordings.request("p", 30)).rejects.toMatchObject({ status: 501 });
    expect(calls).toEqual([]);
  });

  it("sends the bodies the API expects", async () => {
    calls.length = 0;
    await source.org.assignDoctor("p", "d");
    await source.registry.grantDevice("dev", "o");
    await source.registry.setOrganisationStatus("o", "suspended");
    expect(calls.map((call) => call.body)).toEqual([{ doctor_id: "d" }, { org_id: "o" }, { status: "suspended" }]);
  });
});
