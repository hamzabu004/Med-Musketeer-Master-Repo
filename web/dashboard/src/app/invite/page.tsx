import Link from "next/link";
import { AuthCard } from "@/components/auth/auth-card";

export default function InvitePage() {
  return (
    <AuthCard wide>
      <h2 className="font-semibold">Using your invite code</h2>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm">
        <li>Your administrator created your account and gave you an invite code. They see it only once, so keep it until you have signed in.</li>
        <li>
          Open <Link href="/login" className="text-[var(--color-info)] underline">sign-in</Link> and enter the e-mail address your administrator used.
        </li>
        <li>When asked, enter the invite code. Then choose how to sign in from now on: a password, or a passkey on this device.</li>
        <li>You return here signed in, to the pages your role allows.</li>
      </ol>
      <p className="mt-4 text-sm text-[var(--color-text-muted)]">
        If the code was lost or no longer works, ask your administrator. A doctor or patient asks their organisation administrator; an organisation administrator asks the system administrator.
      </p>
    </AuthCard>
  );
}
