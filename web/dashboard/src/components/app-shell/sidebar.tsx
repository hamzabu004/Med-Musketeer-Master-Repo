"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronLeft, ChevronRight, HeartPulse, X } from "lucide-react";
import { useEffect, useState } from "react";
import { navigationByRole } from "@/config/navigation";
import type { Role } from "@/types";
import { cn } from "@/lib/cn";

const STORAGE_KEY = "medmusketeer:poc:sidebar-collapsed";

function NavigationLinks({
  role,
  pathname,
  collapsed = false,
  onNavigate,
}: {
  role: Role;
  pathname: string;
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <nav className="flex-1 space-y-1 p-2" aria-label={`${role} navigation`}>
      {navigationByRole[role].map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            title={collapsed ? item.label : undefined}
            aria-current={active ? "page" : undefined}
            onClick={onNavigate}
            className={cn(
              "flex h-10 items-center gap-3 rounded-[var(--radius-sm)] px-3 text-sm transition-colors",
              active
                ? "bg-[var(--color-accent)] text-[var(--color-on-accent)]"
                : "text-[var(--color-nav-text)] hover:bg-[var(--color-nav-hover)] hover:text-[var(--color-on-brand)]",
            )}
          >
            <Icon size={18} strokeWidth={1.8} aria-hidden />
            {!collapsed && <span>{item.label}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

export function Sidebar({
  role,
  mobileOpen,
  onMobileClose,
}: {
  role: Role;
  mobileOpen: boolean;
  onMobileClose: () => void;
}) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const storedCollapsed = window.localStorage.getItem(STORAGE_KEY) === "1";
    const timer = window.setTimeout(() => setCollapsed(storedCollapsed), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onMobileClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [mobileOpen, onMobileClose]);

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
  };

  return (
    <>
      <aside
        className={cn(
          "hidden min-h-screen shrink-0 border-r border-[var(--color-nav-border)] bg-[var(--color-brand)] text-[var(--color-on-brand)] md:flex md:flex-col",
          collapsed ? "w-[var(--sidebar-collapsed)]" : "w-[var(--sidebar-expanded)]",
        )}
      >
        <div className="flex h-16 items-center gap-3 border-b border-[var(--color-nav-border)] px-4">
          <HeartPulse size={20} strokeWidth={1.8} className="shrink-0 text-[var(--color-accent)]" aria-hidden />
          {!collapsed && <span className="font-semibold">MedMusketeer</span>}
        </div>
        <NavigationLinks role={role} pathname={pathname} collapsed={collapsed} />
        <button
          type="button"
          onClick={toggle}
          className="m-2 flex h-10 items-center justify-center rounded-[var(--radius-sm)] border border-[var(--color-nav-border)] text-[var(--color-nav-text)] hover:bg-[var(--color-nav-hover)]"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-[var(--color-overlay)]"
            aria-label="Close navigation"
            onClick={onMobileClose}
          />
          <aside className="relative flex h-full w-[min(19rem,86vw)] flex-col bg-[var(--color-brand)] text-[var(--color-on-brand)] [box-shadow:var(--shadow-hard)]">
            <div className="flex h-16 items-center gap-3 border-b border-[var(--color-nav-border)] px-4">
              <HeartPulse size={20} strokeWidth={1.8} className="text-[var(--color-accent)]" aria-hidden />
              <span className="font-semibold">MedMusketeer</span>
              <button
                type="button"
                className="ml-auto inline-flex size-9 items-center justify-center rounded-[var(--radius-sm)] hover:bg-[var(--color-nav-hover)]"
                onClick={onMobileClose}
                aria-label="Close navigation"
              >
                <X size={19} strokeWidth={1.8} />
              </button>
            </div>
            <NavigationLinks role={role} pathname={pathname} onNavigate={onMobileClose} />
          </aside>
        </div>
      )}
    </>
  );
}
