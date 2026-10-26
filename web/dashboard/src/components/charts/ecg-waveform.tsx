"use client";

import { useId, useMemo, useState } from "react";

/** Paper speed and gain of a standard ECG strip: 25 mm per second, 10 mm per millivolt. */
export const MM_PER_S = 25;
export const MM_PER_MV = 10;
/** Screen pixels per millimetre of paper, so a strip keeps its proportions on every screen. */
const PX_PER_MM = 4;
/** The segments do not carry the wearable's ADC gain. 200 counts per mV is MIT-BIH's, which the
 * models are trained on and the sample data and seed-dev use; an assumption until the gain is decided. */
export const DEFAULT_COUNTS_PER_MV = 200;

/** The strip's size in millimetres: the duration at paper speed, and the signal's range in mV
 * padded and rounded out to whole large squares (0.5 mV), at least 3 mV tall. */
export function stripGeometry(samples: ArrayLike<number>, fsHz: number, countsPerMv = DEFAULT_COUNTS_PER_MV) {
  let min = 0;
  let max = 0;
  for (let i = 0; i < samples.length; i++) {
    min = Math.min(min, samples[i]);
    max = Math.max(max, samples[i]);
  }
  let top = Math.ceil((max / countsPerMv + 0.25) * 2) / 2;
  let bottom = Math.floor((min / countsPerMv - 0.25) * 2) / 2;
  while (top - bottom < 3) {
    top += 0.5;
    if (top - bottom < 3) bottom -= 0.5;
  }
  const seconds = samples.length / fsHz;
  return { seconds, topMv: top, bottomMv: bottom, widthMm: seconds * MM_PER_S, heightMm: (top - bottom) * MM_PER_MV };
}

export function ECGWaveform({
  samples,
  fsHz,
  label = "ECG",
  countsPerMv = DEFAULT_COUNTS_PER_MV,
}: {
  samples: ArrayLike<number>;
  fsHz: number;
  label?: string;
  countsPerMv?: number;
}) {
  const id = useId();
  const [cursor, setCursor] = useState<number | null>(null);
  const geometry = useMemo(() => stripGeometry(samples, fsHz, countsPerMv), [samples, fsHz, countsPerMv]);
  const { seconds, topMv, widthMm, heightMm } = geometry;
  const y = (count: number) => (topMv - count / countsPerMv) * MM_PER_MV;

  const path = useMemo(() => {
    const parts: string[] = [];
    for (let i = 0; i < samples.length; i++) {
      parts.push(`${i === 0 ? "M" : "L"}${((i / fsHz) * MM_PER_S).toFixed(2)} ${((topMv - samples[i] / countsPerMv) * MM_PER_MV).toFixed(2)}`);
    }
    return parts.join("");
  }, [samples, fsHz, countsPerMv, topMv]);

  if (samples.length === 0) {
    return <p className="rounded-[var(--radius-sm)] border border-[var(--color-border)] p-6 text-center text-sm text-[var(--color-text-muted)]">No ECG samples in this segment.</p>;
  }

  const index = cursor === null ? null : Math.min(samples.length - 1, Math.max(0, Math.round((cursor / MM_PER_S) * fsHz)));
  const summary = `${label}: ${seconds.toFixed(1)} s at ${fsHz} Hz, ${MM_PER_S} mm/s and ${MM_PER_MV} mm/mV.`;

  return (
    <figure className="space-y-2">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-2 text-xs text-[var(--color-text-muted)]">
        <span className="font-medium text-[var(--color-text)]">{label}</span>
        <span>
          {MM_PER_S} mm/s · {MM_PER_MV} mm/mV · {fsHz} Hz · gain {countsPerMv} counts/mV (assumed)
        </span>
      </figcaption>
      <div className="relative overflow-x-auto rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)]">
        <svg
          width={widthMm * PX_PER_MM}
          height={(heightMm + 6) * PX_PER_MM}
          viewBox={`0 0 ${widthMm} ${heightMm + 6}`}
          role="img"
          aria-label={summary}
          className="block touch-pan-x"
          onPointerMove={(event) => {
            const box = event.currentTarget.getBoundingClientRect();
            setCursor(((event.clientX - box.left) / box.width) * widthMm);
          }}
          onPointerLeave={() => setCursor(null)}
        >
          <defs>
            <pattern id={`${id}-small`} width="1" height="1" patternUnits="userSpaceOnUse">
              <path d="M1 0V1H0" fill="none" stroke="rgba(180,70,70,0.12)" strokeWidth="0.1" />
            </pattern>
            <pattern id={`${id}-large`} width="5" height="5" patternUnits="userSpaceOnUse">
              <rect width="5" height="5" fill={`url(#${id}-small)`} />
              <path d="M5 0V5H0" fill="none" stroke="rgba(180,70,70,0.3)" strokeWidth="0.2" />
            </pattern>
          </defs>
          <rect width={widthMm} height={heightMm} fill={`url(#${id}-large)`} />
          {/* 0 mV baseline */}
          <line x1="0" x2={widthMm} y1={y(0)} y2={y(0)} stroke="rgba(180,70,70,0.35)" strokeWidth="0.15" strokeDasharray="1 1" />
          <path d={path} fill="none" stroke="var(--color-brand)" strokeWidth="1.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          {Array.from({ length: Math.floor(seconds) + 1 }, (_, s) => (
            <text key={s} x={s * MM_PER_S + 0.6} y={heightMm + 4} fontSize="3" fill="var(--color-text-muted)">
              {s} s
            </text>
          ))}
          {index !== null && (
            <g pointerEvents="none">
              <line x1={(index / fsHz) * MM_PER_S} x2={(index / fsHz) * MM_PER_S} y1="0" y2={heightMm} stroke="var(--color-info)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
              <circle cx={(index / fsHz) * MM_PER_S} cy={y(samples[index])} r="1" fill="var(--color-info)" stroke="var(--color-surface)" strokeWidth="0.5" />
            </g>
          )}
        </svg>
      </div>
      <p className="metric-number h-4 text-xs text-[var(--color-text-muted)]">
        {index !== null ? `${(index / fsHz).toFixed(3)} s · ${(samples[index] / countsPerMv).toFixed(2)} mV` : "Point at the strip to read time and voltage."}
      </p>
    </figure>
  );
}
