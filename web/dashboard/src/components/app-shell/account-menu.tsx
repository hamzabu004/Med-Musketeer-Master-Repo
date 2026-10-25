"use client";

import { ChevronDown, CircleUserRound, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import type { Role } from "@/types";
import { services } from "@/services";

const roleLabels: Record<Role, string> = {
  patient: "Patient",
  doctor: "Doctor",
  admin: "Organization Administrator",
};

export function AccountMenu({ role }: { role: Role }) {
  const router = useRouter();

  async function logout() {
    await services.auth.logout();
    router.replace("/login");
  }

  return (
    <details className="group relative ml-3 shrink-0">
      <summary className="flex h-9 cursor-pointer list-none items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2 hover:bg-[var(--color-surface-subtle)]">
        <CircleUserRound size={18} strokeWidth={1.8} aria-hidden />
        <span className="hidden text-sm sm:inline">{roleLabels[role]}</span>
        <ChevronDown size={14} strokeWidth={1.8} aria-hidden />
        <span className="sr-only">Open account menu</span>
      </summary>
      <div className="absolute right-0 z-40 mt-2 w-48 rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] p-1 [box-shadow:var(--shadow-hard)]">
        <button
          type="button"
          onClick={logout}
          className="flex h-9 w-full items-center gap-2 rounded-[var(--radius-sm)] px-2 text-left text-sm hover:bg-[var(--color-surface-subtle)]"
        >
          <LogOut size={16} strokeWidth={1.8} aria-hidden />
          Logout
        </button>
      </div>
    </details>
  );
}
