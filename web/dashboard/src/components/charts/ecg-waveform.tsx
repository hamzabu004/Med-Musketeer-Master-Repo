"use client";

export function ECGWaveform({
  values,
  label = "Simulated ECG",
  live = false,
}: {
  values: number[];
  label?: string;
  live?: boolean;
}) {
  const width = 900;
  const height = 220;
  const stableAmplitude = 20;
  const step = width / Math.max(values.length - 1, 1);
  const path = values
    .map((value, index) => {
      const x = index * step;
      const y = height / 2 - (value / stableAmplitude) * (height * 0.38);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <div className="overflow-hidden rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-text-muted)]">
        <span>{label}</span>
        <span>{live ? "Live-style signal" : "Recorded signal"}</span>
      </div>
      <div className="clinical-grid relative">
        <svg viewBox={`0 0 ${width} ${height}`} className="block h-56 w-full" role="img" aria-label={label}>
          <path
            d={path}
            fill="none"
            stroke="var(--color-brand)"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
            pathLength={live ? 1 : undefined}
            className={live ? "ecg-live-path" : undefined}
          />
        </svg>
        {values.length === 0 && (
          <p className="absolute inset-0 grid place-items-center text-sm text-[var(--color-text-muted)]">
            No signal available
          </p>
        )}
      </div>
    </div>
  );
}
