"use client";

import { useCallback, useEffect, useState } from "react";
import { services } from "@/services";
import { ServiceError, type DemoSession, type Device, type Doctor, type MonitoringStation, type Organization, type Patient, type SecurityEvent, type SystemPreferences, type User } from "@/types";

export interface AdminOverview {
  session: DemoSession;
  organization: Organization;
  user: User;
  users: User[];
  patients: Patient[];
  doctors: Doctor[];
  devices: Device[];
  stations: MonitoringStation[];
  securityEvents: SecurityEvent[];
  preferences: SystemPreferences;
}

type State = { status: "loading" } | { status: "success"; data: AdminOverview } | { status: "error"; message: string };

async function load(): Promise<AdminOverview> {
  const session = services.auth.getSession();
  if (!session || session.role !== "admin") throw new ServiceError("FORBIDDEN", "An Organization Administrator session is required.");
  const [organization, user, users, patients, doctors, devices, stations, securityEvents, preferences] = await Promise.all([
    services.organizations.get(session.organizationId), services.identities.getUser(session.organizationId, session.userId), services.identities.listUsers(session.organizationId), services.patients.list(session.organizationId), services.doctors.list(session.organizationId),
    services.devices.list(session.organizationId), services.monitoringStations.list(session.organizationId), services.security.listEvents(session.organizationId), services.settings.get(session.organizationId),
  ]);
  if (!organization) throw new ServiceError("NOT_FOUND", "Organization not found.");
  if (!user) throw new ServiceError("NOT_FOUND", "Organization Administrator account not found.");
  return { session, organization, user, users, patients, doctors, devices, stations, securityEvents, preferences };
}

export function useAdminOverview() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [request, setRequest] = useState(0);
  useEffect(() => {
    let active = true;
    load().then((data) => active && setState({ status: "success", data })).catch((error: unknown) => {
      if (active) setState({ status: "error", message: error instanceof Error ? error.message : "Administration data is unavailable." });
    });
    return () => { active = false; };
  }, [request]);
  const refresh = useCallback(() => { setState({ status: "loading" }); setRequest((value) => value + 1); }, []);
  return { state, refresh };
}
