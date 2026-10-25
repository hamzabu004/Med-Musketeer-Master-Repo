import type { PermissionAction, Role } from "@/types";

export const roleHome: Record<Role, string> = {
  patient: "/patient/dashboard",
  doctor: "/doctor/dashboard",
  admin: "/admin/dashboard",
};

const permissions: Record<Role, ReadonlySet<PermissionAction>> = {
  patient: new Set(["view-own-clinical-data"]),
  doctor: new Set([
    "view-assigned-clinical-data",
    "acknowledge-clinical-alert",
  ]),
  admin: new Set([
    "manage-devices",
    "manage-monitoring-stations",
    "manage-identities",
    "manage-security-events",
    "manage-system-settings",
  ]),
};

export function canAccessRoute(role: Role, pathname: string): boolean {
  return pathname === `/${role}` || pathname.startsWith(`/${role}/`);
}

export function canPerform(role: Role, action: PermissionAction): boolean {
  return permissions[role].has(action);
}
