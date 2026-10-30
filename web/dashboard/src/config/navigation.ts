import {
  Bell,
  Building2,
  CircleUserRound,
  FlaskConical,
  HeartPulse,
  LayoutDashboard,
  MonitorCog,
  RadioTower,
  ScrollText,
  ShieldCheck,
  UserCog,
  Users,
} from "lucide-react";
import type { Role } from "@/auth/roles";

export interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
}

export const navigationByRole: Record<Role, NavItem[]> = {
  system_admin: [
    { label: "Dashboard", href: "/system/dashboard", icon: LayoutDashboard },
    { label: "Organisations", href: "/system/organisations", icon: Building2 },
    { label: "Devices", href: "/system/devices", icon: MonitorCog },
    { label: "Security Events", href: "/system/security-events", icon: ShieldCheck },
    { label: "Attack Tests", href: "/system/attack-tests", icon: FlaskConical },
    { label: "Audit Log", href: "/system/audit", icon: ScrollText },
    { label: "Account", href: "/system/account", icon: UserCog },
  ],
  org_admin: [
    { label: "Dashboard", href: "/org/dashboard", icon: LayoutDashboard },
    { label: "Accounts", href: "/org/accounts", icon: Users },
    { label: "Patients", href: "/org/patients", icon: CircleUserRound },
    { label: "Devices", href: "/org/devices", icon: MonitorCog },
    { label: "Gateways", href: "/org/gateways", icon: RadioTower },
    { label: "Audit Log", href: "/org/audit", icon: ScrollText },
    { label: "Account", href: "/org/account", icon: UserCog },
  ],
  doctor: [
    { label: "Dashboard", href: "/doctor/dashboard", icon: LayoutDashboard },
    { label: "Patients", href: "/doctor/patients", icon: CircleUserRound },
    { label: "Alerts", href: "/doctor/alerts", icon: Bell },
    { label: "Account", href: "/doctor/account", icon: UserCog },
  ],
  patient: [
    { label: "Dashboard", href: "/patient/dashboard", icon: LayoutDashboard },
    { label: "Alerts", href: "/patient/alerts", icon: Bell },
    { label: "ECG Recordings", href: "/patient/ecg", icon: HeartPulse },
    { label: "Account", href: "/patient/account", icon: UserCog },
  ],
};
