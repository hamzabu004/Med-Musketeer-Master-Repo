/** Synthetic ECG for sample data, the same generator as the cloud's seed-dev (app/dev_seed.py): a
 * sum of Gaussian waves per beat at 360 Hz, MIT-BIH gain. It carries no clinical meaning. */
export const FS_HZ = 360;
const ADC_PER_MV = 200;

type Wave = [amplitude: number, centre: number, width: number];
const NORMAL: Wave[] = [[0.12, -0.2, 0.025], [-0.12, -0.03, 0.01], [1.1, 0, 0.012], [-0.25, 0.035, 0.012], [0.3, 0.26, 0.045]];
const ECTOPIC: Wave[] = [[1.6, 0, 0.035], [-0.4, 0.07, 0.03], [-0.45, 0.3, 0.07]]; // PVC-like: no P, wide QRS, inverted T

function beat(t: number, ectopic: boolean): number {
  return (ectopic ? ECTOPIC : NORMAL).reduce((mv, [a, mu, w]) => mv + a * Math.exp(-((t - mu) ** 2) / (2 * w * w)), 0);
}

/** A seeded generator (mulberry32), so sample data is the same on every load. */
export function seededRandom(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function syntheticEcg(seconds: number, bpm: number, ectopicEvery: number | null, random: () => number): Int16Array {
  const peaks: [number, boolean][] = [];
  for (let t = 0.4, index = 1; t < seconds + 1; index++) {
    const ectopic = ectopicEvery !== null && index % ectopicEvery === 0;
    peaks.push([t, ectopic]);
    t += (60 / bpm) * (ectopic ? 0.75 : 1) * (0.96 + random() * 0.08);
  }
  const samples = new Int16Array(seconds * FS_HZ);
  for (let i = 0; i < samples.length; i++) {
    const x = i / FS_HZ;
    let mv = 0;
    for (const [peak, ectopic] of peaks) if (x - peak > -0.5 && x - peak < 0.6) mv += beat(x - peak, ectopic);
    mv += 0.05 * Math.sin(2 * Math.PI * 0.3 * x) + (random() - 0.5) * 0.02; // baseline wander, noise
    samples[i] = Math.max(-32768, Math.min(32767, Math.round(mv * ADC_PER_MV)));
  }
  return samples;
}
