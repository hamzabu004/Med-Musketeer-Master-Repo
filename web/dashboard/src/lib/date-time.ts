export type TimeRange = "3h" | "6h" | "12h" | "24h" | "7d" | "30d";

const rangeMilliseconds: Record<TimeRange, number> = {
  "3h": 3 * 60 * 60 * 1000,
  "6h": 6 * 60 * 60 * 1000,
  "12h": 12 * 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
};

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-PK", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Karachi",
  }).format(new Date(value));
}

export function formatChartTime(value: string): string {
  return new Intl.DateTimeFormat("en-PK", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Karachi",
  }).format(new Date(value));
}

export function filterByRange<T>(
  items: T[],
  range: TimeRange,
  timestampOf: (item: T) => string,
  referenceTimestamps: string[] = [],
): T[] {
  const timestamps = [...items.map(timestampOf), ...referenceTimestamps]
    .map(Date.parse)
    .filter(Number.isFinite);
  if (timestamps.length === 0) return items;

  const reference = Math.max(...timestamps);
  const cutoff = reference - rangeMilliseconds[range];
  return items.filter((item) => Date.parse(timestampOf(item)) >= cutoff);
}
