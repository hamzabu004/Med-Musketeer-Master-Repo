import { describe, expect, it } from "vitest";
import type { Device, RevocationStatus } from "@/api/types";
import { gatewayListState } from "./revocation-list";

const gateway = (over: Partial<Device> = {}): Device => ({
  device_id: "11111111-1111-4111-8111-111111111111", type: "fixed_gateway", status: "active", is_testbed: true,
  current_mode: "fixed", current_gateway_id: null, last_seen: null, status_changed_at: "2026-10-30T10:00:00Z",
  revocation_version: 3, registered_by: null, created_at: "2026-10-01T10:00:00Z", ...over,
});
const status = (published: number): RevocationStatus => ({ version: published, published_version: published, published_at: null, stale_gateways: [] });

describe("a gateway against the revocation list (D16)", () => {
  it("is current when it reports the published version", () => {
    expect(gatewayListState(gateway(), status(3))).toEqual({ label: "Current (v3)", tone: "healthy", stale: false });
  });

  it("is stale when behind or silent, as the API's stale_gateways", () => {
    expect(gatewayListState(gateway({ revocation_version: 2 }), status(3))).toMatchObject({ label: "Behind: v2 of v3", stale: true });
    expect(gatewayListState(gateway({ revocation_version: null }), status(3))).toMatchObject({ label: "Not reported (current v3)", stale: true });
  });

  it("does not apply before a list is published, to wearables, or to inactive gateways", () => {
    expect(gatewayListState(gateway({ revocation_version: null }), status(0))).toMatchObject({ stale: false });
    expect(gatewayListState(gateway({ type: "wearable" }), status(3))).toBeNull();
    expect(gatewayListState(gateway({ status: "suspended", revocation_version: 1 }), status(3))).toBeNull();
  });
});
