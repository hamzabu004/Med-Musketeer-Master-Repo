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

export interface DoctorOverview {
  session: DemoSession;
  user: User;
  doctor: Doctor;
  patients: Patient[];
  stations: MonitoringStation[];
  devices: Device[];
  alerts: ClinicalAlert[];
  events: ECGEvent[];
  ecgRequests: ECGRequest[];
  readings: HeartRateReading[];
  preferences: SystemPreferences;
}

type DoctorOverviewState =
  | { status: "loading" }
  | { status: "success"; data: DoctorOverview }
  | { status: "error"; message: string };

async function loadDoctorOverview(): Promise<DoctorOverview> {
  const session = services.auth.getSession();
  if (!session || session.role !== "doctor") {
    throw new ServiceError("FORBIDDEN", "A Doctor session is required.");
  }

  const doctor = await services.doctors.getByUserId(session.organizationId, session.userId);
  if (!doctor) throw new ServiceError("NOT_FOUND", "Clinician profile not found.");

  const [user, patients, stations, alerts, preferences] = await Promise.all([
    services.identities.getUser(session.organizationId, session.userId),
    services.patients.getAssignedPatients(session.organizationId, doctor.id),
    services.monitoringStations.listAssignedToDoctor(session.organizationId, doctor.id),
    services.clinicalAlerts.listForDoctor(session.organizationId, doctor.id),
    services.settings.get(session.organizationId),
  ]);
  if (!user) throw new ServiceError("NOT_FOUND", "Clinician account not found.");

  const patientIds = patients.map((patient) => patient.id);
  const [devices, eventGroups, ecgRequests, readingGroups] = await Promise.all([
    services.devices.listForPatients(session.organizationId, patientIds),
    Promise.all(patientIds.map((patientId) => services.ecg.listEventsForPatient(session.organizationId, patientId))),
    services.ecg.listRequestsForPatients(session.organizationId, patientIds),
    Promise.all(patientIds.map((patientId) => services.ecg.listHeartRateReadings(session.organizationId, patientId))),
  ]);

  return {
    session,
    user,
    doctor,
    patients,
    stations,
    devices,
    alerts,
    events: eventGroups.flat(),
    ecgRequests,
    readings: readingGroups.flat(),
    preferences,
  };
}

export function useDoctorOverview() {
  const [request, setRequest] = useState(0);
  const [state, setState] = useState<DoctorOverviewState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    loadDoctorOverview()
      .then((data) => {
        if (active) setState({ status: "success", data });
      })
      .catch((error: unknown) => {
        if (!active) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Clinical monitoring data is unavailable.",
        });
      });
    return () => {
      active = false;
    };
  }, [request]);

  useEffect(() => {
    if (state.status !== "success") return;
    const interval = window.setInterval(() => {
      setRequest((value) => value + 1);
    }, state.data.preferences.heartRateMonitoringIntervalSeconds * 1000);
    return () => window.clearInterval(interval);
  }, [state]);

  return {
    state,
    retry: () => {
      setState({ status: "loading" });
      setRequest((value) => value + 1);
    },
  };
}
