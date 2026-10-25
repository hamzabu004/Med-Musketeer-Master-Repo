"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ECGEvent } from "@/types";

const tooltipStyle = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border-strong)",
  borderRadius: "var(--radius-sm)",
  boxShadow: "none",
  fontSize: 12,
};

export function EventFrequencyChart({ events }: { events: ECGEvent[] }) {
  const counts = new Map<string, number>();
  for (const event of events) {
    const label = new Intl.DateTimeFormat("en-PK", {
      day: "2-digit",
      month: "short",
      timeZone: "Asia/Karachi",
    }).format(new Date(event.timestamp));
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  const data = [...counts].map(([date, count]) => ({ date, count }));

  return (
    <div className="h-56 w-full" role="img" aria-label="ECG event frequency by date">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="var(--color-border)" vertical={false} />
          <XAxis dataKey="date" tickLine={false} axisLine={false} fontSize={12} />
          <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} width={30} />
          <Tooltip contentStyle={tooltipStyle} formatter={(value) => [value, "Events"]} />
          <Bar dataKey="count" fill="var(--color-accent)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ClassificationDistributionChart({ events }: { events: ECGEvent[] }) {
  const data = ["normal", "abnormal", "unclassified"].map((classification) => ({
    classification: classification[0].toUpperCase() + classification.slice(1),
    count: events.filter((event) => event.classification === classification).length,
  }));

  return (
    <div className="h-56 w-full" role="img" aria-label="ECG classification distribution">
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 8, right: 12, bottom: 4, left: 8 }}>
          <CartesianGrid stroke="var(--color-border)" horizontal={false} />
          <XAxis type="number" allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} />
          <YAxis type="category" dataKey="classification" tickLine={false} axisLine={false} fontSize={12} width={84} />
          <Tooltip contentStyle={tooltipStyle} formatter={(value) => [value, "Events"]} />
          <Bar dataKey="count" fill="var(--color-brand)" radius={[0, 2, 2, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
