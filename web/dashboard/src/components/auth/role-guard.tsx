"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { roleHome, type Role } from "@/auth/roles";
import { useSession } from "@/auth/session";
import { Skeleton } from "@/components/ui/skeleton";

export const ACCESS_DENIED_MESSAGE_KEY = "medmusketeer:dashboard:access-denied";

/** Renders a role's area only for that role; anyone else goes to sign-in or their own area. A UX
 * guard only: the API refuses what a role may not do (D9). */
export function RoleGuard({ role, children }: { role: Role; children: React.ReactNode }) {
  const router = useRouter();
  const { state } = useSession();
  const allowed = state.status === "signedIn" && state.session.role === role;

  useEffect(() => {
    if (state.status === "loading" || allowed) return;
    if (state.status === "signedIn") {
      window.sessionStorage.setItem(ACCESS_DENIED_MESSAGE_KEY, "That page belongs to another role. You were returned to your dashboard.");
      router.replace(roleHome(state.session.role));
    } else {
      router.replace("/login");
    }
  }, [state, allowed, router]);

  if (!allowed) {
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
