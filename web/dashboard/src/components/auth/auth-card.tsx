import { HeartPulse } from "lucide-react";

/** The centred card of the pages outside the shell (sign-in, callback, invite help). */
export function AuthCard({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  return (
    <main className="grid min-h-screen place-items-center bg-[var(--color-bg)] p-4">
      <section
        className={`w-full ${wide ? "max-w-lg" : "max-w-sm"} rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] p-6`}
      >
        <div className="mb-6 flex items-center gap-3">
          <HeartPulse size={24} strokeWidth={1.8} className="text-[var(--color-accent)]" aria-hidden />
          <div>
            <h1 className="text-xl font-semibold">MedMusketeer</h1>
            <p className="text-xs text-[var(--color-text-muted)]">Clinical monitoring</p>
          </div>
        </div>
        {children}
        <p className="mt-5 border-t border-[var(--color-border)] pt-4 text-xs text-[var(--color-text-muted)]">
          Research prototype, not a medical device. Do not use it for diagnosis or treatment.
        </p>
      </section>
    </main>
  );
}
