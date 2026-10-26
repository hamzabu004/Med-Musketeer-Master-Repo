import type { AuditEvent } from "@/api/types";
import { labelize, shortId } from "./labels";

/** An audit row's details as one readable line: ids short (or named, through `nameOf`), roles as
 * labels, nested values as JSON. Shared by the registry and organisation audit tables. */
export function formatAuditDetails(event: AuditEvent, nameOf: (key: string, id: string) => string | null = () => null): string {
  return Object.entries(event.details ?? {})
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => {
      let shown: string;
      if (typeof value === "object") shown = JSON.stringify(value);
      else if (key.endsWith("_id")) shown = nameOf(key, String(value)) ?? shortId(String(value));
      else if (key === "role") shown = labelize(String(value));
      else shown = String(value);
      return `${labelize(key.replace(/_id$/, ""))}: ${shown}`;
    })
    .join(" · ");
}
