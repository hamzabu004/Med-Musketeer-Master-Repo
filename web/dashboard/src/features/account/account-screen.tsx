"use client";

import { roleLabels } from "@/auth/roles";
import { useData, useSession } from "@/auth/session";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageIntro } from "@/components/ui/page-intro";
import { dataSource } from "@/config/capabilities";
import { useResource } from "@/lib/use-resource";

/** The signed-in user's own account, for every role. Names come from ZITADEL through /directory
 * (not for the system admin, who has no directory); the password is changed in ZITADEL. */
export function AccountScreen() {
  const { session, data } = useData();
  const { signOut } = useSession();
  const details = useResource(async () => {
    if (session.role === "system_admin") return { person: null, organisation: null };
    const [people, organisation] = await Promise.all([data.directory(), data.organisation()]);
    return { person: people.find((p) => p.user_id === session.userId) ?? null, organisation };
  }, [session.userId]);

  const person = details.status === "ready" ? details.data.person : null;
  const organisation = details.status === "ready" ? details.data.organisation : null;
  const rows: [string, React.ReactNode][] = [
    ["Name", person ? `${person.given_name ?? ""} ${person.family_name ?? ""}`.trim() || "—" : session.role === "system_admin" ? "Shown in ZITADEL" : "—"],
    ["Role", roleLabels[session.role]],
    ["Organisation", organisation?.name ?? (session.role === "system_admin" ? "All (registry)" : "—")],
    ["Account id", <span key="id" className="font-mono text-xs">{session.userId}</span>],
  ];

  return (
    <section className="mx-auto max-w-3xl space-y-5">
      <PageIntro title="Account" />
      <Card className="p-4">
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          {rows.map(([term, value]) => (
            <div key={term}>
              <dt className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">{term}</dt>
              <dd className="mt-0.5 break-all">{value}</dd>
            </div>
          ))}
        </dl>
      </Card>
      <Card className="space-y-3 p-4 text-sm">
        <p className="text-[var(--color-text-muted)]">
          {dataSource === "mock"
            ? "This is a sample account; signing out discards the changes made in this tab."
            : "Your name, e-mail and password are kept by the sign-in service (ZITADEL). To change your password, use \"Reset password\" on the sign-in page."}
        </p>
        <Button type="button" variant="secondary" onClick={() => void signOut()}>Sign out</Button>
      </Card>
    </section>
  );
}
