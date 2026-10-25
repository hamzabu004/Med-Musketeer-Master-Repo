"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export function HeartRateTrend({
  data,
}: {
  data: Array<{ time: string; bpm: number | null }>;
}) {
  return (
    <div className="h-64 w-full" role="img" aria-label="Heart rate trend in beats per minute">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--color-border)" vertical={false} />
          <XAxis dataKey="time" tickLine={false} axisLine={false} fontSize={12} />
          <YAxis tickLine={false} axisLine={false} fontSize={12} width={38} />
          <Tooltip
            contentStyle={{
              background: "var(--color-surface)",
              border: "1px solid var(--color-border-strong)",
              borderRadius: "var(--radius-sm)",
              boxShadow: "none",
              fontSize: 12,
            }}
            formatter={(value) => [`${value} bpm`, "Heart rate"]}
          />
          <Line
            type="monotone"
            dataKey="bpm"
            stroke="var(--color-accent)"
            strokeWidth={2}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
