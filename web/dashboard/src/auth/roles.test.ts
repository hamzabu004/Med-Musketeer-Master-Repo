import { describe, expect, it } from "vitest";
import { ROLES, canAccessRoute, roleHome } from "./roles";

describe("roles", () => {
  it("match the cloud's four roles", () => {
    expect([...ROLES].sort()).toEqual(["doctor", "org_admin", "patient", "system_admin"]);
  });

  it("send each role to its own dashboard", () => {
    expect(roleHome("system_admin")).toBe("/system/dashboard");
    expect(roleHome("org_admin")).toBe("/org/dashboard");
    expect(roleHome("doctor")).toBe("/doctor/dashboard");
    expect(roleHome("patient")).toBe("/patient/dashboard");
  });

  it("keep each role inside its own area", () => {
    expect(canAccessRoute("doctor", "/doctor")).toBe(true);
    expect(canAccessRoute("doctor", "/doctor/patients/p1")).toBe(true);
    expect(canAccessRoute("doctor", "/doctors")).toBe(false);
    expect(canAccessRoute("org_admin", "/doctor/alerts")).toBe(false);
    expect(canAccessRoute("system_admin", "/patient/ecg")).toBe(false);
  });
});
