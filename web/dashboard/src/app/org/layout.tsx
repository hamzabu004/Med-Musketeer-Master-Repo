import { RoleArea } from "@/components/app-shell/role-area";

export default function OrgLayout({ children }: { children: React.ReactNode }) {
  return <RoleArea role="org_admin">{children}</RoleArea>;
}
