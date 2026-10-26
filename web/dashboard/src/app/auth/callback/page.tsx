"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { userManager } from "@/auth/oidc";
import { useSession } from "@/auth/session";
import { AuthCard } from "@/components/auth/auth-card";
import { Skeleton } from "@/components/ui/skeleton";

/** Where ZITADEL returns after sign-in: exchanges the code for tokens (PKCE), then goes home. */
export default function AuthCallbackPage() {
  const router = useRouter();
  const { reload } = useSession();
  const [failed, setFailed] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return; // the code can be exchanged once (React strict mode runs effects twice)
    started.current = true;
    (async () => {
      try {
        await (await userManager()).signinCallback();
        await reload();
        router.replace("/");
      } catch {
        setFailed(true);
      }
    })();
  }, [reload, router]);

  return (
    <AuthCard>
      {failed ? (
        <div role="alert" className="space-y-3 text-sm">
          <p>Sign-in could not be completed. The link may have expired or been used already.</p>
          <Link href="/login" className="text-[var(--color-info)] underline">
            Back to sign-in
          </Link>
        </div>
      ) : (
        <div aria-busy="true" aria-label="Completing sign-in" className="space-y-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-9 w-full" />
        </div>
      )}
    </AuthCard>
  );
}
