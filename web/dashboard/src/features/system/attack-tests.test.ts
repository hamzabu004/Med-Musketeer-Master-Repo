import { describe, expect, it } from "vitest";
import type { SecurityEvent } from "@/api/types";
import { covers } from "./attack-tests";

const test0 = { test_id: "t", target_device_id: "d", triggered_by: "u", attack_type: "syn_flood", parameters: {}, started_at: "2026-10-01T00:00:00Z", ended_at: "2026-10-01T00:02:00Z" };
const event = (ts: string): SecurityEvent => ({ event_id: ts, ts, gateway_id: "g", device_id: "x", mode: "ids", predicted_class: "benign", outcome: "no_threat", action: null, action_result: null });

describe("attack test coverage", () => {
  it("trusts a page of events that is not full", () => {
    expect(covers(test0, [event("2026-10-20T00:00:00Z")])).toBe(true);
  });

  it("does not call a window missed when the full page of events starts after it", () => {
    const newer = Array.from({ length: 1000 }, (_, i) => event(new Date(Date.parse("2026-10-20T00:00:00Z") + i * 1000).toISOString()));
    expect(covers(test0, newer)).toBe(false);
    expect(covers(test0, [...newer.slice(1), event("2026-09-30T00:00:00Z")])).toBe(true);
  });
});
