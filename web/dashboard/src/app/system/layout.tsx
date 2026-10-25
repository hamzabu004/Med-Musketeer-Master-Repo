import { AppShell } from "@/components/app-shell/app-shell";
import { RoleGuard } from "@/components/auth/role-guard";

export default function SystemLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard role="system_admin">
      <AppShell role="system_admin" title="System Administration">{children}</AppShell>
    </RoleGuard>
  );
}
