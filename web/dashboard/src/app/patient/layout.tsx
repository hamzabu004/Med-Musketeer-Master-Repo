import { AppShell } from "@/components/app-shell/app-shell";
import { RoleGuard } from "@/components/auth/role-guard";

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard role="patient">
      <AppShell role="patient" title="My Monitoring">{children}</AppShell>
    </RoleGuard>
  );
}
