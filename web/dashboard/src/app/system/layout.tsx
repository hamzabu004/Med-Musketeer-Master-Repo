import { RoleArea } from "@/components/app-shell/role-area";

export default function SystemLayout({ children }: { children: React.ReactNode }) {
  return <RoleArea role="system_admin">{children}</RoleArea>;
}
