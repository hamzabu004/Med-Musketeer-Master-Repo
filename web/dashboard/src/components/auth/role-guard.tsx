"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { roleHome, type Role } from "@/auth/roles";
import { getSession } from "@/auth/session";
import { Skeleton } from "@/components/ui/skeleton";

export const ACCESS_DENIED_MESSAGE_KEY = "medmusketeer:dashboard:access-denied";

export function RoleGuard({
  role,
  children,
}: {
  role: Role;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);

  useEffect(() => {
    const session = getSession();
    if (!session) {
      router.replace("/login");
      return;
    }

    if (session.role !== role) {
      window.sessionStorage.setItem(
        ACCESS_DENIED_MESSAGE_KEY,
        "Access denied. You were returned to your dashboard.",
      );
      router.replace(roleHome(session.role));
      return;
    }

    const timer = window.setTimeout(() => setAuthorized(true), 0);
    return () => window.clearTimeout(timer);
  }, [role, router]);

  if (!authorized) {
    return (
      <main className="grid min-h-screen place-items-center bg-[var(--color-bg)] p-6" aria-busy="true">
        <div className="w-full max-w-sm space-y-3" aria-label="Checking session">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-12 w-full" />
        </div>
      </main>
    );
  }

  return children;
}
