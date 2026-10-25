"use client";

import { MonitoringStationCard } from "@/components/monitoring/monitoring-station-card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageIntro } from "@/components/ui/page-intro";
import { DoctorPageError, DoctorPageSkeleton } from "./doctor-page-state";
import { useDoctorOverview } from "./use-doctor-overview";

export function DoctorMonitoringStations() {
  const { state, retry } = useDoctorOverview();
  if (state.status === "loading") return <DoctorPageSkeleton />;
  if (state.status === "error") return <DoctorPageError message={state.message} onRetry={retry} />;

  const patientNames = new Map(state.data.patients.map((patient) => [patient.id, patient.displayName]));

  return (
    <section className="mx-auto max-w-7xl space-y-5">
      <PageIntro
        title="Monitoring Stations"
        description="Connectivity and registered-patient context for your clinical monitoring area."
      />
      <p className="text-sm text-[var(--color-text-muted)]">
        This view is read-only and does not expose global network or security configuration.
      </p>
      {state.data.stations.length ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {state.data.stations.map((station) => (
            <MonitoringStationCard
              key={station.id}
              station={station}
              associatedPatientNames={station.patientIds
                .map((patientId) => patientNames.get(patientId))
                .filter((name): name is string => Boolean(name))}
            />
          ))}
        </div>
      ) : (
        <EmptyState title="No assigned Monitoring Stations" description="No Monitoring Stations are assigned to this clinician." />
      )}
    </section>
  );
}
