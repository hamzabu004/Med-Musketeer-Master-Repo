import { AppShell } from "@/components/app-shell/app-shell";
import { RoleGuard } from "@/components/auth/role-guard";

export default function OrgLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard role="org_admin">
      <AppShell role="org_admin" title="Organisation Administration">{children}</AppShell>
    </RoleGuard>
  );
}
