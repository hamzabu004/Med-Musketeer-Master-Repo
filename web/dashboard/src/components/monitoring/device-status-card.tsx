import type { Device } from "@/types";
import { Card } from "@/components/ui/card";
import { Status } from "@/components/ui/status";

export function DeviceStatusCard({ device }: { device: Device }) {
  const tone = device.status === "online" ? "healthy" : device.status === "pending" ? "warning" : "offline";
  const statusLabel = device.status === "online" ? "Connected" : device.status[0].toUpperCase() + device.status.slice(1);

  return (
    <Card className="p-4">
      <p className="text-sm font-medium">Wearable Device</p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <dt className="text-[var(--color-text-muted)]">Status</dt><dd><Status label={statusLabel} tone={tone} /></dd>
        <dt className="text-[var(--color-text-muted)]">Battery</dt><dd>{device.batteryPercent == null ? "—" : `${device.batteryPercent}%`}</dd>
      </dl>
    </Card>
  );
}
