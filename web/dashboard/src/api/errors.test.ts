import { describe, expect, it } from "vitest";
import { ApiError, detailMessage, errorFromResponse, userMessage } from "./errors";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("API errors", () => {
  it("read every shape of FastAPI's detail", () => {
    expect(detailMessage("alert already acknowledged")).toBe("alert already acknowledged");
    expect(detailMessage({ error: "conflicts with an existing record", constraint: "devices_pkey" })).toBe("conflicts with an existing record");
    expect(detailMessage([{ loc: ["body", "credential_ref"], msg: "Value error, 64 hex digits" }])).toBe("credential_ref: Value error, 64 hex digits");
    expect(detailMessage(undefined)).toBeNull();
  });

  it("keep the status and the raw detail", async () => {
    const error = await errorFromResponse(json(409, { detail: { error: "conflicts with an existing record", constraint: "x" } }));
    expect(error).toMatchObject({ status: 409, message: "conflicts with an existing record", detail: { constraint: "x" } });
  });

  it("survive a body that is not JSON", async () => {
    const error = await errorFromResponse(new Response("<html>bad gateway</html>", { status: 502, statusText: "Bad Gateway" }));
    expect(error).toMatchObject({ status: 502, message: "Bad Gateway" });
  });

  it("do not tell the user whether a 404 exists or is out of reach", () => {
    expect(userMessage(new ApiError(404, "patient not found"))).toBe("Not found, or not available to you.");
    expect(userMessage(new ApiError(409, "the wearable is suspended"))).toBe("the wearable is suspended");
    expect(userMessage(new ApiError(0, "unreachable"))).toMatch(/could not be reached/);
  });
});

describe("API errors, review findings (Phase 3)", () => {
  it("fall back to the status when HTTP/2 sends no status text", async () => {
    const error = await errorFromResponse(new Response("", { status: 429 }));
    expect(error.message).toBe("HTTP 429");
  });
});
