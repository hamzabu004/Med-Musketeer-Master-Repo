import type { Role } from "@/auth/roles";
import { RoleGuard } from "@/components/auth/role-guard";
import { AppShell } from "./app-shell";

const areaTitles: Record<Role, string> = {
  system_admin: "System Administration",
  org_admin: "Organisation Administration",
  doctor: "Clinical Monitoring",
  patient: "My Monitoring",
};

/** The layout of a role's area: only that role gets in, inside the shell. */
export function RoleArea({ role, children }: { role: Role; children: React.ReactNode }) {
  return (
    <RoleGuard role={role}>
      <AppShell role={role} title={areaTitles[role]}>{children}</AppShell>
    </RoleGuard>
  );
}
