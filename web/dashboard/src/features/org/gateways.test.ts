import { describe, expect, it } from "vitest";
import { formatDuration } from "@/lib/date-time";
import { eventLabel } from "./gateway-detail";
import { connection } from "./gateways";

const NOW = Date.parse("2026-10-30T12:00:00Z");
const ago = (minutes: number) => new Date(NOW - minutes * 60_000).toISOString();

describe("a gateway's connection", () => {
  it("gives uptime in its two largest units", () => {
    expect(formatDuration(ago(0.5), NOW)).toBe("under a minute");
    expect(formatDuration(ago(12), NOW)).toBe("12 min");
    expect(formatDuration(ago(200), NOW)).toBe("3 h 20 min");
    expect(formatDuration(ago(180), NOW)).toBe("3 h");
    expect(formatDuration(ago(60 * 51), NOW)).toBe("2 d 3 h");
  });

  it("reads up, down, or not reported", () => {
    expect(connection({ state: "online", since: ago(200) }, NOW)).toMatchObject({ label: "Online", tone: "healthy", detail: "Up 3 h 20 min" });
    expect(connection({ state: "offline", since: ago(5) }, NOW)).toMatchObject({ label: "Offline", tone: "critical", detail: "Down 5 min" });
    expect(connection({ state: "unknown", since: null }, NOW).label).toBe("Not reported");
  });

  it("names log rows by who changed: the gateway's cloud session or a wearable on it", () => {
    expect(eventLabel({ device_type: "fixed_gateway", state: "offline" })).toBe("Disconnected from the cloud");
    expect(eventLabel({ device_type: "wearable", state: "online" })).toBe("Wearable joined");
  });
});
