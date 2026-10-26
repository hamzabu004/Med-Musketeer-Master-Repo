"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { roleHome } from "@/auth/roles";
import { useSession } from "@/auth/session";
import { Skeleton } from "@/components/ui/skeleton";

export default function HomePage() {
  const router = useRouter();
  const { state } = useSession();

  useEffect(() => {
    if (state.status === "loading") return;
    router.replace(state.status === "signedIn" ? roleHome(state.session.role) : "/login");
  }, [state, router]);

  return (
    <main className="grid min-h-screen place-items-center bg-[var(--color-bg)] p-6" aria-busy="true">
      <Skeleton className="h-12 w-full max-w-sm" />
    </main>
  );
}
