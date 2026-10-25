import { MockAuthService } from "./mock/mock-auth-service";
import { MockOrganizationService } from "./mock/mock-organization-service";
import { MockDeviceService } from "./mock/mock-device-service";
import { MockMonitoringStationService } from "./mock/mock-monitoring-station-service";
import { MockPatientService } from "./mock/mock-patient-service";
import { MockSecurityService } from "./mock/mock-security-service";
import { MockClinicalAlertService } from "./mock/mock-clinical-alert-service";
import { MockDemoStateService } from "./mock/mock-demo-state-service";
import { MockDoctorService } from "./mock/mock-doctor-service";
import { MockECGService } from "./mock/mock-ecg-service";
import { MockIdentityService } from "./mock/mock-identity-service";
import { MockSettingsService } from "./mock/mock-settings-service";

export const services = {
  auth: new MockAuthService(),
  organizations: new MockOrganizationService(),
  patients: new MockPatientService(),
  doctors: new MockDoctorService(),
  clinicalAlerts: new MockClinicalAlertService(),
  ecg: new MockECGService(),
  devices: new MockDeviceService(),
  monitoringStations: new MockMonitoringStationService(),
  identities: new MockIdentityService(),
  security: new MockSecurityService(),
  settings: new MockSettingsService(),
  demoState: new MockDemoStateService(),
};
