"use client";

import { useEffect, useState } from "react";
import { services } from "@/services";
import {
  ServiceError,
  type ClinicalAlert,
  type DemoSession,
  type Device,
  type Doctor,
  type ECGEvent,
  type ECGRequest,
  type HeartRateReading,
  type MonitoringStation,
  type Patient,
  type SystemPreferences,
  type User,
} from "@/types";

export interface PatientOverview {
  session: DemoSession;
  user: User;
  patient: Patient;
  doctor: Doctor | null;
  device: Device | null;
  station: MonitoringStation | null;
  alerts: ClinicalAlert[];
  events: ECGEvent[];
  ecgRequests: ECGRequest[];
  readings: HeartRateReading[];
  preferences: SystemPreferences;
}

type PatientOverviewState =
  | { status: "loading" }
  | { status: "success"; data: PatientOverview }
  | { status: "error"; message: string };

async function loadPatientOverview(): Promise<PatientOverview> {
  const session = services.auth.getSession();
  if (!session || session.role !== "patient") {
    throw new ServiceError("FORBIDDEN", "A Patient session is required.");
  }

  const patient = await services.patients.getPatientByUserId(session.organizationId, session.userId);
  if (!patient) throw new ServiceError("NOT_FOUND", "Patient profile not found.");

  const [user, doctor, device, station, alerts, events, ecgRequests, readings, preferences] = await Promise.all([
    services.identities.getUser(session.organizationId, session.userId),
    patient.assignedDoctorIds[0]
      ? services.doctors.get(session.organizationId, patient.assignedDoctorIds[0])
      : Promise.resolve(null),
    patient.deviceId ? services.devices.get(session.organizationId, patient.deviceId) : Promise.resolve(null),
    patient.monitoringStationId
      ? services.monitoringStations.get(session.organizationId, patient.monitoringStationId)
      : Promise.resolve(null),
    services.clinicalAlerts.listForPatient(session.organizationId, patient.id),
    services.ecg.listEventsForPatient(session.organizationId, patient.id),
    services.ecg.listRequestsForPatient(session.organizationId, patient.id),
    services.ecg.listHeartRateReadings(session.organizationId, patient.id),
    services.settings.get(session.organizationId),
  ]);

  if (!user) throw new ServiceError("NOT_FOUND", "Account not found.");

  return { session, user, patient, doctor, device, station, alerts, events, ecgRequests, readings, preferences };
}

export function usePatientOverview() {
  const [request, setRequest] = useState(0);
  const [state, setState] = useState<PatientOverviewState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    loadPatientOverview()
      .then((data) => {
        if (active) setState({ status: "success", data });
      })
      .catch((error: unknown) => {
        if (!active) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Patient information is unavailable.",
        });
      });
    return () => {
      active = false;
    };
  }, [request]);

  return {
    state,
    retry: () => {
      setState({ status: "loading" });
      setRequest((value) => value + 1);
    },
  };
}
