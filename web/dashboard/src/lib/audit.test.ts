import { describe, expect, it } from "vitest";
import type { AuditEvent } from "@/api/types";
import { formatAuditDetails } from "./audit";

const event = (details: Record<string, unknown>): AuditEvent => ({
  event_id: "e", at: "2026-10-26T00:00:00Z", actor_id: "a", scope: "organisation", org_id: null, action: "x.y", target_id: null, details,
});

describe("audit details", () => {
  it("shows nested values as JSON, not [object Object] (Phase 5 review)", () => {
    expect(formatAuditDetails(event({ params: { rate_pps: 100 } }))).toBe('Params: {"rate_pps":100}');
  });

  it("shortens ids unless a name is known, labels roles and skips empty values", () => {
    const id = "3f2b6c1e-8a4d-4f0e-9b7a-1c2d3e4f5a6b";
    expect(formatAuditDetails(event({ device_id: id, role: "org_admin", previous_doctor_id: null }))).toBe("Device: 3f2b6c1e · Role: Org admin");
    expect(formatAuditDetails(event({ doctor_id: id }), () => "Sarah Ahmed")).toBe("Doctor: Sarah Ahmed");
  });
});
