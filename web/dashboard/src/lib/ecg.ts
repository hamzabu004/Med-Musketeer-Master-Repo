/** ECG samples as the API sends them: each chunk holds int16 little-endian samples in base64
 * (`encoding: "int16le-base64"`) at the segment's `fs_hz`. */
import type { Chunk } from "@/api/types";

export function decodeSamples(base64: string): Int16Array {
  const binary = atob(base64);
  const view = new DataView(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i++) view.setUint8(i, binary.charCodeAt(i));
  const samples = new Int16Array(Math.floor(binary.length / 2));
  for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true);
  return samples;
}

export function encodeSamples(samples: ArrayLike<number>): string {
  const view = new DataView(new ArrayBuffer(samples.length * 2));
  for (let i = 0; i < samples.length; i++) view.setInt16(i * 2, samples[i], true);
  let binary = "";
  for (let i = 0; i < view.byteLength; i++) binary += String.fromCharCode(view.getUint8(i));
  return btoa(binary);
}

/** A segment's samples in order: chunks sorted by `seq`, each decoded and cut to `n_samples`. */
export function stitchChunks(chunks: readonly Chunk[]): Int16Array {
  const decoded = [...chunks].sort((a, b) => a.seq - b.seq).map((chunk) => decodeSamples(chunk.samples).subarray(0, chunk.n_samples));
  const out = new Int16Array(decoded.reduce((total, part) => total + part.length, 0));
  let offset = 0;
  for (const part of decoded) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}
