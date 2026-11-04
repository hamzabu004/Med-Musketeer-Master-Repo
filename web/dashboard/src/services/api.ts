import { ApiError } from "@/api/errors";
import type { DataSource } from "./contracts";
import type { Http } from "./http";

const id = encodeURIComponent;

const notServed = (): Promise<never> => Promise.reject(new ApiError(501, "not served by the cloud yet"));

/** The data source backed by the cloud API. */
export function createApiDataSource(http: Http): DataSource {
  const get = <T>(path: string, query?: Record<string, string | number | boolean | undefined>) =>
    http<T>("GET", path, { query });
  const post = <T>(path: string, body?: unknown) => http<T>("POST", path, { body });

  return {
    me: () => get("/me"),
    organisation: () => get("/organisation"),
    directory: () => get("/directory"),

    registry: {
      organisations: () => get("/admin/organisations"),
      createOrganisation: (body) => post("/admin/organisations", body),
      setOrganisationStatus: (orgId, status) => http("PATCH", `/admin/organisations/${id(orgId)}`, { body: { status } }),
      createOrganisationAdmin: (orgId, body) => post(`/admin/organisations/${id(orgId)}/admins`, body),
      devices: () => get("/admin/devices"),
      device: (deviceId) => get(`/admin/devices/${id(deviceId)}`),
      registerDevice: (body) => post("/admin/devices", body),
      activateDevice: (deviceId) => post(`/admin/devices/${id(deviceId)}/activate`),
      suspendDevice: (deviceId) => post(`/admin/devices/${id(deviceId)}/suspend`),
      revokeDevice: (deviceId) => post(`/admin/devices/${id(deviceId)}/revoke`),
      credentials: (deviceId) => get(`/admin/devices/${id(deviceId)}/credentials`),
      addCredential: (deviceId, body) => post(`/admin/devices/${id(deviceId)}/credentials`, body),
      revokeCredential: (credentialId) => post(`/admin/credentials/${id(credentialId)}/revoke`),
      grants: (deviceId) => get(`/admin/devices/${id(deviceId)}/grants`),
      grantDevice: (deviceId, orgId) => post(`/admin/devices/${id(deviceId)}/grants`, { org_id: orgId }),
      revokeGrant: (grantId) => post(`/admin/grants/${id(grantId)}/revoke`),
      audit: (limit) => get("/admin/audit", { limit }),
      securityEvents: (limit) => get("/admin/security-events", { limit }),
      revocation: () => get("/admin/revocation"),
    },

    // Not served by the cloud yet (Iteration 5); screens check isAvailable("attackTests") first.
    attackTests: {
      list: notServed,
      start: notServed,
      stop: notServed,
    },

    // Not served by the cloud yet (on-demand start/stop is open); screens check isAvailable("ecgRequests").
    recordings: {
      list: notServed,
      request: notServed,
    },

    org: {
      accounts: () => get("/accounts"),
      createAccount: (body) => post("/accounts", body),
      disableAccount: (userId) => post(`/accounts/${id(userId)}/disable`),
      assignDoctor: (patientId, doctorId) => http("PUT", `/patients/${id(patientId)}/doctor`, { body: { doctor_id: doctorId } }),
      issueWearable: (patientId, deviceId) => post(`/patients/${id(patientId)}/wearable`, { device_id: deviceId }),
      returnWearable: (patientId) => http("DELETE", `/patients/${id(patientId)}/wearable`),
      recordDisorder: (patientId, disorder) => post(`/patients/${id(patientId)}/disorders`, { disorder }),
      exportPatient: (patientId, destination) => post(`/patients/${id(patientId)}/exports`, { destination }),
      audit: (limit) => get("/audit", { limit }),
    },

    gateways: {
      list: () => get("/gateways"),
      detail: (gatewayId) => get(`/gateways/${id(gatewayId)}`),
      connectivity: (gatewayId, limit) => get(`/gateways/${id(gatewayId)}/connectivity`, { limit }),
      alerts: (gatewayId, limit) => get(`/gateways/${id(gatewayId)}/alerts`, { limit }),
    },

    patients: () => get("/patients"),
    disorders: (patientId) => get(`/patients/${id(patientId)}/disorders`),
    devices: () => get("/devices"),

    care: {
      alerts: (query = {}) => get("/alerts", { ...query }),
      patientAlerts: (patientId, query = {}) => get(`/patients/${id(patientId)}/alerts`, { ...query }),
      acknowledge: (alertId) => post(`/alerts/${id(alertId)}/acknowledge`),
      segments: (patientId, limit) => get(`/patients/${id(patientId)}/segments`, { limit }),
      segment: (segmentId) => get(`/segments/${id(segmentId)}`),
    },
  };
}
