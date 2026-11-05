import { describe, expect, it } from "vitest";
import type { OrgGateway } from "@/api/types";
import { gatewayListState } from "./revocation-list";

type Gateway = Pick<OrgGateway, "status" | "revocation">;
const gateway = (reported: number | null, published: number, current: boolean, status = "active"): Gateway =>
  ({ status, revocation: { reported_version: reported, published_version: published, current } });

describe("a gateway against the revocation list (D16), as the org admin sees it", () => {
  it("is current when it reports the published version", () => {
    expect(gatewayListState(gateway(3, 3, true))).toEqual({ label: "Current (v3)", tone: "healthy", stale: false });
  });

  it("is stale when behind or silent, as the API says", () => {
    expect(gatewayListState(gateway(2, 3, false))).toMatchObject({ label: "Behind: v2 of v3", stale: true });
    expect(gatewayListState(gateway(null, 3, false))).toMatchObject({ label: "Not reported (current v3)", stale: true });
  });

  it("does not apply before a list is published, or to inactive gateways", () => {
    expect(gatewayListState(gateway(null, 0, true))).toMatchObject({ label: "No list published yet", stale: false });
    expect(gatewayListState(gateway(1, 3, true, "suspended"))).toBeNull();
  });
});
