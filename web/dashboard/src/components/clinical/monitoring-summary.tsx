import { Card } from "@/components/ui/card";
import { Status } from "@/components/ui/status";
import { formatDateTime } from "@/lib/date-time";
import type { ECGClassification } from "@/types";

export function MonitoringSummary({
  heartRate,
  classification,
  latestHeartRateAt,
  heartRateIntervalSeconds,
}: {
  heartRate: number | null;
  classification: ECGClassification;
  latestHeartRateAt?: string;
  heartRateIntervalSeconds?: number;
}) {
  const classificationTone =
    classification === "normal" ? "healthy" : classification === "abnormal" ? "critical" : "offline";
  const stale =
    !latestHeartRateAt || (heartRateIntervalSeconds ? Date.now() - Date.parse(latestHeartRateAt) > heartRateIntervalSeconds * 2000 : false);

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Card className="p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">Heart rate</p>
        <p className="mt-2 text-3xl font-semibold metric-number">
          {heartRate ?? "—"} <span className="text-sm font-normal text-[var(--color-text-muted)]">BPM</span>
        </p>
        {latestHeartRateAt && (
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
            <span className="text-[var(--color-text-muted)] metric-number">{formatDateTime(latestHeartRateAt)}</span>
            <Status label={stale ? "Stale reading" : "Current reading"} tone={stale ? "warning" : "healthy"} />
          </div>
        )}
      </Card>
      <Card className="p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">ECG classification</p>
        <div className="mt-3">
          <Status
            label={classification[0].toUpperCase() + classification.slice(1)}
            tone={classificationTone}
          />
        </div>
      </Card>
    </div>
  );
}
