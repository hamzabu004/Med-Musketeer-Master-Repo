"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { roleHome, roleLabels } from "@/auth/roles";
import { useSession } from "@/auth/session";
import { AuthCard } from "@/components/auth/auth-card";
import { SessionProblem } from "@/components/auth/session-problem";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { dataSource } from "@/config/capabilities";
import { sampleWorld } from "@/services/mock/sample-session";

function SampleAccounts({ onPick }: { onPick: (userId: string) => void }) {
  const users = sampleWorld().users.filter((user) => user.status === "active");
  return (
    <div className="space-y-3">
      <p className="text-sm text-[var(--color-text-muted)]">
        This deployment shows <strong>sample data</strong>, not real patients. Choose an account to see its role.
      </p>
      <ul className="divide-y divide-[var(--color-border)] rounded-[var(--radius-sm)] border border-[var(--color-border)]">
        {users.map((user) => (
          <li key={user.user_id}>
            <button
              type="button"
              onClick={() => onPick(user.user_id)}
              className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-[var(--color-surface-subtle)]"
            >
              <span className="font-medium">
                {user.given_name} {user.family_name}
              </span>
              <span className="text-xs text-[var(--color-text-muted)]">{roleLabels[user.role]}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { state, signIn } = useSession();
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    if (state.status === "signedIn") router.replace(roleHome(state.session.role));
  }, [state, router]);

  async function startSignIn() {
    setRedirecting(true);
    try {
      await signIn();
    } catch {
      setRedirecting(false);
    }
  }

  let body: React.ReactNode;
  if (state.status === "loading" || state.status === "signedIn") {
    body = <Skeleton className="h-9 w-full" />;
  } else if (state.status === "error") {
    body = <SessionProblem title="Sign-in is unavailable" message={state.message} />;
  } else if (state.status === "noAccess") {
    body = <SessionProblem title="No access" message={state.message} />;
  } else if (dataSource === "mock") {
    body = <SampleAccounts onPick={(userId) => void signIn(userId)} />;
  } else {
    body = (
      <div className="space-y-4">
        {state.message && <p className="text-sm text-[var(--color-warning)]">{state.message}</p>}
        <Button className="w-full" onClick={() => void startSignIn()} disabled={redirecting}>
          {redirecting ? "Opening sign-in…" : "Sign in"}
        </Button>
        <p className="text-xs text-[var(--color-text-muted)]">
          New account? <Link href="/invite" className="text-[var(--color-info)] underline">How to use your invite code</Link>
        </p>
      </div>
    );
  }

  return <AuthCard wide={dataSource === "mock"}>{body}</AuthCard>;
}
