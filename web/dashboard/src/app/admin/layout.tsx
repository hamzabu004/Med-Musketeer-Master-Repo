import { AppShell } from "@/components/app-shell/app-shell";
import { RoleGuard } from "@/components/auth/role-guard";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard role="admin">
      <AppShell role="admin" title="Organization Administration">{children}</AppShell>
    </RoleGuard>
  );
}
