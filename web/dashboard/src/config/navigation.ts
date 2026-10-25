import {
  Activity,
  Bell,
  CircleUserRound,
  HeartPulse,
  History,
  LayoutDashboard,
  MonitorCog,
  RadioTower,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Stethoscope,
  Users,
} from "lucide-react";
import type { Role } from "@/types";

export interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
}

export const navigationByRole: Record<Role, NavItem[]> = {
  patient: [
    { label: "Dashboard", href: "/patient/dashboard", icon: LayoutDashboard },
    { label: "My Monitoring", href: "/patient/monitoring", icon: HeartPulse },
    { label: "My History", href: "/patient/history", icon: History },
    { label: "Alerts", href: "/patient/alerts", icon: Bell },
    { label: "Settings", href: "/patient/settings", icon: Settings },
  ],
  doctor: [
    { label: "Dashboard", href: "/doctor/dashboard", icon: LayoutDashboard },
    { label: "Patients", href: "/doctor/patients", icon: CircleUserRound },
    { label: "Alerts", href: "/doctor/alerts", icon: Bell },
    { label: "Monitoring Stations", href: "/doctor/monitoring-stations", icon: RadioTower },
    { label: "History", href: "/doctor/history", icon: History },
    { label: "Settings", href: "/doctor/settings", icon: Settings },
  ],
  admin: [
    { label: "Dashboard", href: "/admin/dashboard", icon: LayoutDashboard },
    { label: "Users & Identity", href: "/admin/identities", icon: Users },
    { label: "Patients", href: "/admin/patients", icon: Activity },
    { label: "Clinicians", href: "/admin/clinicians", icon: Stethoscope },
    { label: "Devices", href: "/admin/devices", icon: MonitorCog },
    { label: "Monitoring Stations", href: "/admin/monitoring-stations", icon: RadioTower },
    { label: "Security", href: "/admin/security", icon: ShieldCheck },
    { label: "Organization Configuration", href: "/admin/system-configuration", icon: SlidersHorizontal },
    { label: "Settings", href: "/admin/settings", icon: Settings },
  ],
};
