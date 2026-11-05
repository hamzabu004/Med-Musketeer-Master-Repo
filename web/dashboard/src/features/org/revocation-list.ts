/** A gateway's state against the wearable revocation list (cloud-backend.md D16, D17). Gateways
 * report the list version they enforce in their status; one that has not reported the published
 * version may still let a revoked wearable in. The API decides `current` (only active gateways can
 * be behind, and only once a list has been published); this only labels it for the org admin. */
import type { OrgGateway } from "@/api/types";
import type { StatusTone } from "@/components/ui/status";

export interface ListState {
  label: string;
  tone: StatusTone;
  stale: boolean;
}

export function gatewayListState(gateway: Pick<OrgGateway, "status" | "revocation">): ListState | null {
  if (gateway.status !== "active") return null;
  const { reported_version: reported, published_version: published, current } = gateway.revocation;
  if (published === 0) return { label: "No list published yet", tone: "info", stale: false };
  if (current) return { label: `Current (v${reported ?? published})`, tone: "healthy", stale: false };
  if (reported === null) return { label: `Not reported (current v${published})`, tone: "warning", stale: true };
  return { label: `Behind: v${reported} of v${published}`, tone: "warning", stale: true };
}
