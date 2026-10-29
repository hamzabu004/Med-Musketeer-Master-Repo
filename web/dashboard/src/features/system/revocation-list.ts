/** A gateway's state against the wearable revocation list (cloud-backend.md D16). Gateways report
 * the list version they enforce in their status; one that has not reported the published version
 * may still let a revoked wearable in. Same rule as the API's `stale_gateways`: only active
 * gateways count, and only once a list has been published. */
import type { Device, RevocationStatus } from "@/api/types";
import type { StatusTone } from "@/components/ui/status";

export interface ListState {
  label: string;
  tone: StatusTone;
  stale: boolean;
}

export function gatewayListState(device: Device, revocation: RevocationStatus): ListState | null {
  if (device.type !== "fixed_gateway" || device.status !== "active") return null;
  const published = revocation.published_version;
  if (published === 0) return { label: "No list published yet", tone: "info", stale: false };
  const reported = device.revocation_version;
  if (reported === null) return { label: `Not reported (current v${published})`, tone: "warning", stale: true };
  if (reported < published) return { label: `Behind: v${reported} of v${published}`, tone: "warning", stale: true };
  return { label: `Current (v${reported})`, tone: "healthy", stale: false };
}
