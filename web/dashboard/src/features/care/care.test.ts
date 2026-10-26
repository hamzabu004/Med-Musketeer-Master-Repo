import { afterEach, describe, expect, it, vi } from "vitest";
import { stripGeometry } from "@/components/charts/ecg-waveform";
import { beatLabel } from "@/lib/labels";
import { severityTone } from "./alert-table";
import { countLabel } from "./limits";
import type { RecordingRequest } from "@/services/contracts";
import { recordingState } from "./recording-panel";
import { markRendered, RENDER_MARK } from "./render-mark";

describe("the ECG strip keeps paper proportions", () => {
  it("is 25 mm per second wide and whole large squares tall, at least 3 mV", () => {
    const flat = new Int16Array(3600); // 10 s at 360 Hz
    expect(stripGeometry(flat, 360)).toMatchObject({ seconds: 10, widthMm: 250, heightMm: 30 });
    const peaks = Int16Array.from({ length: 360 }, (_, i) => (i === 100 ? 400 : i === 200 ? -150 : 0)); // +2 mV, -0.75 mV at 200 counts/mV
    const g = stripGeometry(peaks, 360);
    expect(g.topMv).toBe(2.5);
    expect(g.bottomMv).toBe(-1);
    expect(g.heightMm).toBe(35);
  });
});

describe("recording requests read as the command's state", () => {
  const request = (extra: Partial<RecordingRequest>): RecordingRequest => ({
    command_id: "c", patient_id: "p", device_id: "d", issued_by: "u", type: "ecg_recording", path: "fixed", status: "sent",
    created_at: "2026-10-26T00:00:00Z", acked_at: null, duration_s: 30, segment_id: null, ...extra,
  });
  it("is open until the segment arrives, and closed when it expires", () => {
    expect(recordingState(request({})).open).toBe(true);
    expect(recordingState(request({ status: "acked", acked_at: "2026-10-26T00:00:03Z" }))).toMatchObject({ label: "Recording", open: true });
    expect(recordingState(request({ status: "acked", segment_id: "s" }))).toMatchObject({ label: "Recorded", open: false });
    expect(recordingState(request({ status: "expired" }))).toMatchObject({ label: "No answer from the wearable", open: false });
  });
});

describe("the dashboard-render checkpoint", () => {
  afterEach(() => vi.restoreAllMocks());
  it("marks each alert once, with its id and creation time", () => {
    const mark = vi.spyOn(performance, "mark");
    const alert = { alert_id: "a-render-1", created_at: "2026-10-26T00:00:00Z" };
    markRendered([alert]);
    markRendered([alert]);
    expect(mark).toHaveBeenCalledTimes(1);
    expect(mark).toHaveBeenCalledWith(RENDER_MARK, { detail: { ...alert, backlog: true } }); // created before the page loaded
    markRendered([{ alert_id: "a-render-2", created_at: new Date(performance.timeOrigin + 1000).toISOString() }]);
    expect(mark).toHaveBeenLastCalledWith(RENDER_MARK, { detail: expect.objectContaining({ backlog: false }) });
  });
});

describe("classification labels", () => {
  it("names AAMI classes and passes others through", () => {
    expect(beatLabel("V")).toBe("Ventricular ectopic (V)");
    expect(beatLabel("custom")).toBe("custom");
    expect(beatLabel(null)).toBe("Not classified");
  });
});

describe("review findings (Phase 6)", () => {
  it("never shows an unexpected severity as calm", () => {
    expect(severityTone("critical")).toBe("critical");
    expect(severityTone("urgent")).toBe("warning");
    expect(severityTone("low")).toBe("info");
  });

  it("says when a count comes from a full, capped list", () => {
    expect(countLabel(999)).toBe("999");
    expect(countLabel(1000)).toBe("1000+");
  });
});
