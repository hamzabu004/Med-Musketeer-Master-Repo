import { RoleArea } from "@/components/app-shell/role-area";

export default function DoctorLayout({ children }: { children: React.ReactNode }) {
  return <RoleArea role="doctor">{children}</RoleArea>;
}
