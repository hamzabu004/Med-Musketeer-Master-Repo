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

/** "just now", "5 min ago", "3 h ago", "2 d ago"; a missing time reads "never". */
export function formatAgo(value: string | null, now = Date.now()): string {
  if (!value) return "never";
  const seconds = Math.max(0, Math.round((now - Date.parse(value)) / 1000));
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86_400)} d ago`;
}

/** How long since `value`, in its two largest units: "2 d 3 h", "3 h 20 min", "12 min", "under a minute". */
export function formatDuration(value: string, now = Date.now()): string {
  const minutes = Math.max(0, Math.floor((now - Date.parse(value)) / 60_000));
  if (minutes < 1) return "under a minute";
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  if (days) return hours ? `${days} d ${hours} h` : `${days} d`;
  if (hours) return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
  return `${minutes} min`;
}
