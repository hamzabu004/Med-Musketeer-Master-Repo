import { ECGWaveform } from "@/components/charts/ecg-waveform";
import { ConnectionNotice } from "@/components/monitoring/connection-notice";
import { DeviceStatusCard } from "@/components/monitoring/device-status-card";
import { MonitoringStationCard } from "@/components/monitoring/monitoring-station-card";
import { EmptyState } from "@/components/ui/empty-state";
import type { Device, Doctor, ECGEvent, HeartRateReading, MonitoringStation, Patient, SystemPreferences } from "@/types";
import { ECGEventList } from "./ecg-event-list";
import { MonitoringSummary } from "./monitoring-summary";
import { PatientIdentity } from "./patient-identity";

export function PatientMonitoringPanel({
  patient,
  clinician,
  device,
  station,
  events,
  readings = [],
  preferences,
  eventLimit = 5,
  showLiveEcg = true,
}: {
  patient: Patient;
  clinician: Doctor | null;
  device: Device | null;
  station: MonitoringStation | null;
  events: ECGEvent[];
  readings?: HeartRateReading[];
  preferences?: SystemPreferences;
  eventLimit?: number;
  showLiveEcg?: boolean;
}) {
  const recentEvents = [...events].sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  const latestReading = [...readings]
    .filter((reading) => reading.patientId === patient.id)
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))[0];
  const latestWaveform = recentEvents[0]?.waveform ?? [];
  const liveWaveform = Array.from({ length: 8 }, () => latestWaveform).flat();
  const signalAvailable = device?.status === "online" && station?.status === "online";

  return (
    <div className="space-y-5">
      <PatientIdentity name={patient.displayName} clinicianName={clinician?.displayName} />
      <ConnectionNotice device={device} station={station} classification={patient.ecgClassification} />
      <MonitoringSummary
        heartRate={latestReading?.bpm ?? patient.currentHeartRate}
        classification={patient.ecgClassification}
        latestHeartRateAt={latestReading?.timestamp ?? patient.lastUpdatedAt}
        heartRateIntervalSeconds={preferences?.heartRateMonitoringIntervalSeconds}
      />

      <section aria-labelledby="live-ecg-heading" className="space-y-3">
        <div>
          <h3 id="live-ecg-heading" className="text-lg font-semibold">{showLiveEcg ? "Simulated ECG" : "Latest ECG Recording"}</h3>
        </div>
        {showLiveEcg && signalAvailable && liveWaveform.length ? (
          <ECGWaveform values={liveWaveform} live label="Simulated live-style ECG waveform" />
        ) : !showLiveEcg && latestWaveform.length ? (
          <ECGWaveform values={latestWaveform} label="Latest ECG recording" />
        ) : (
          <>
            <ECGWaveform values={[]} label="Simulated ECG signal unavailable" />
            <p className="text-sm text-[var(--color-warning)]">
              {showLiveEcg
                ? "Live-style updates are unavailable because the monitoring connection is not active."
                : "No completed ECG recording is available for this patient."}
            </p>
          </>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {device ? (
          <DeviceStatusCard device={device} />
        ) : (
          <EmptyState title="No wearable assigned" description="Wearable information is unavailable for this profile." />
        )}
        {station ? (
          <MonitoringStationCard station={station} />
        ) : (
          <EmptyState title="No Monitoring Station assigned" description="Monitoring Station information is unavailable for this profile." />
        )}
      </div>

      <section aria-labelledby="monitoring-events-heading" className="min-w-0 space-y-3">
        <h3 id="monitoring-events-heading" className="text-lg font-semibold">Recent monitoring events</h3>
        {recentEvents.length ? (
          <ECGEventList events={recentEvents.slice(0, eventLimit)} />
        ) : (
          <EmptyState title="No monitoring events" description="No ECG events are available for this patient." />
        )}
      </section>
    </div>
  );
}
