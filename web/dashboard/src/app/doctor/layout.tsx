import { AppShell } from "@/components/app-shell/app-shell";
import { RoleGuard } from "@/components/auth/role-guard";

export default function DoctorLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard role="doctor">
      <AppShell role="doctor" title="Clinical Monitoring">{children}</AppShell>
    </RoleGuard>
  );
}
