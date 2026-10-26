/** The API's largest page of alerts or segments (`limit` le=1000). */
export const ALERT_LIMIT = 1000;

/** A count read from a capped list: "1000+" when the list is full, since there may be more. */
export function countLabel(count: number, limit = ALERT_LIMIT): string {
  return count >= limit ? `${limit}+` : String(count);
}
