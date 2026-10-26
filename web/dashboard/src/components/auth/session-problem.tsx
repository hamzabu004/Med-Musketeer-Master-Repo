"use client";

import { useSession } from "@/auth/session";
import { Button } from "@/components/ui/button";

/** Signed in at ZITADEL but refused by the API, or the server unreachable: say so, offer a way out. */
export function SessionProblem({ title, message }: { title: string; message: string }) {
  const { state, signOut, reload } = useSession();
  return (
    <div role="alert" className="space-y-4">
      <div>
        <h2 className="font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">{message}</p>
      </div>
      <div className="flex gap-2">
        <Button type="button" variant="secondary" onClick={() => void reload()}>
          Try again
        </Button>
        {state.status === "noAccess" && (
          <Button type="button" onClick={() => void signOut()}>
            Sign out
          </Button>
        )}
      </div>
    </div>
  );
}
