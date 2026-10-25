/** The four ZITADEL project roles (cloud `app.auth.ROLES`). The API enforces what each may do (D9);
 * the dashboard only uses the role to pick the area and navigation. */
export const ROLES = ["system_admin", "org_admin", "doctor", "patient"] as const;

export type Role = (typeof ROLES)[number];

/** The URL segment of each role's area. */
export const roleArea: Record<Role, string> = {
  system_admin: "system",
  org_admin: "org",
  doctor: "doctor",
  patient: "patient",
};

export const roleLabels: Record<Role, string> = {
  system_admin: "System Administrator",
  org_admin: "Organisation Administrator",
  doctor: "Doctor",
  patient: "Patient",
};

export function roleHome(role: Role): string {
  return `/${roleArea[role]}/dashboard`;
}

/** Whether `pathname` is `base` or a page below it. */
export function isWithin(pathname: string, base: string): boolean {
  return pathname === base || pathname.startsWith(`${base}/`);
}

/** Whether `pathname` lies in the role's area. A UX guard only: the API decides access. */
export function canAccessRoute(role: Role, pathname: string): boolean {
  return isWithin(pathname, `/${roleArea[role]}`);
}
