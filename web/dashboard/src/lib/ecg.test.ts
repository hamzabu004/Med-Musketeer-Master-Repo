import { describe, expect, it } from "vitest";
import type { Chunk } from "@/api/types";
import { decodeSamples, encodeSamples, stitchChunks } from "./ecg";

describe("ecg samples", () => {
  it("round-trip int16 little-endian through base64, including the extremes", () => {
    const samples = [0, 1, -1, 220, -90, 32767, -32768];
    expect(Array.from(decodeSamples(encodeSamples(samples)))).toEqual(samples);
  });

  it("decode the byte order the API sends (little-endian)", () => {
    expect(Array.from(decodeSamples(btoa(String.fromCharCode(0x01, 0x02, 0xff, 0xff))))).toEqual([0x0201, -1]);
  });

  it("stitch chunks by seq, not by arrival order, and honour n_samples", () => {
    const chunk = (seq: number, samples: number[], n = samples.length): Chunk => ({
      seq, ts: "2026-10-25T00:00:00Z", n_samples: n, encoding: "int16le-base64", samples: encodeSamples(samples),
    });
    const out = stitchChunks([chunk(1, [3, 4]), chunk(0, [1, 2, 99], 2)]);
    expect(Array.from(out)).toEqual([1, 2, 3, 4]);
  });
});
