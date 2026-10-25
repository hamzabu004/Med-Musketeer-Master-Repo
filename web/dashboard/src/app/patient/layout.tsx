import { RoleArea } from "@/components/app-shell/role-area";

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  return <RoleArea role="patient">{children}</RoleArea>;
}
