"use client";

import { useEffect, useState } from "react";
import type { Role } from "@/auth/roles";
import { ACCESS_DENIED_MESSAGE_KEY } from "@/components/auth/role-guard";
import { AppHeader } from "./app-header";
import { Sidebar } from "./sidebar";

export function AppShell({
  role,
  title,
  children,
}: {
  role: Role;
  title: string;
  children: React.ReactNode;
}) {
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    const message = window.sessionStorage.getItem(ACCESS_DENIED_MESSAGE_KEY);
    if (!message) return;
    window.sessionStorage.removeItem(ACCESS_DENIED_MESSAGE_KEY);
    const timer = window.setTimeout(() => setToast(message), 0);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <div className="min-h-screen bg-[var(--color-bg)] md:flex">
      <Sidebar
        role={role}
        mobileOpen={mobileNavigationOpen}
        onMobileClose={() => setMobileNavigationOpen(false)}
      />
      <div className="min-w-0 flex-1">
        <AppHeader
          role={role}
          title={title}
          onOpenNavigation={() => setMobileNavigationOpen(true)}
        />
        <main className="p-4 md:p-6">{children}</main>
      </div>
      {toast && (
        <div
          role="status"
          className="fixed bottom-4 right-4 z-50 max-w-sm rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-4 py-3 text-sm [box-shadow:var(--shadow-hard)]"
        >
          {toast}
          <button
            type="button"
            className="ml-4 font-medium text-[var(--color-info)]"
            onClick={() => setToast("")}
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
