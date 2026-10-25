import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import type { Device, ECGClassification, MonitoringStation } from "@/types";

export function ConnectionNotice({
  device,
  station,
  classification,
}: {
  device: Device | null;
  station: MonitoringStation | null;
  classification: ECGClassification;
}) {
  const deviceConnected = device?.status === "online";
  const stationConnected = station?.status === "online";
  const connectionInterrupted = !deviceConnected || !stationConnected;

  if (connectionInterrupted) {
    return (
      <Card className="border-[var(--color-warning)] bg-[var(--color-surface)] p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 shrink-0 text-[var(--color-warning)]" size={19} aria-hidden />
          <div>
            <h3 className="font-semibold">Monitoring connection needs attention</h3>
          </div>
        </div>
      </Card>
    );
  }

  if (classification === "abnormal") {
    return (
      <Card className="border-[var(--color-critical)] p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 shrink-0 text-[var(--color-critical)]" size={19} aria-hidden />
          <div>
            <h3 className="font-semibold">An abnormal ECG event was recorded</h3>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card className="border-[var(--color-healthy)] p-4">
      <div className="flex items-start gap-3">
        <CheckCircle2 className="mt-0.5 shrink-0 text-[var(--color-healthy)]" size={19} aria-hidden />
        <div>
          <h3 className="font-semibold">Monitoring is active</h3>
        </div>
      </div>
    </Card>
  );
}
