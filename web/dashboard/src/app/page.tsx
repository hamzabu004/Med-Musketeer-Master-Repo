"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { roleHome } from "@/auth/roles";
import { getSession } from "@/auth/session";
import { Skeleton } from "@/components/ui/skeleton";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const session = getSession();
    router.replace(session ? roleHome(session.role) : "/login");
  }, [router]);

  return (
    <main className="grid min-h-screen place-items-center bg-[var(--color-bg)] p-6" aria-busy="true">
      <Skeleton className="h-12 w-full max-w-sm" />
    </main>
  );
}
