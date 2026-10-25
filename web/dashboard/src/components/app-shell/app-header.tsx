import { Menu } from "lucide-react";
import type { Role } from "@/auth/roles";
import { AccountMenu } from "./account-menu";

export function AppHeader({
  role,
  title,
  onOpenNavigation,
}: {
  role: Role;
  title: string;
  onOpenNavigation: () => void;
}) {
  return (
    <header className="flex min-h-16 items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-[var(--color-border)] md:hidden"
          onClick={onOpenNavigation}
          aria-label="Open navigation"
        >
          <Menu size={19} strokeWidth={1.8} />
        </button>
        <h1 className="truncate text-lg font-semibold tracking-tight md:text-xl">{title}</h1>
      </div>
      <AccountMenu role={role} />
    </header>
  );
}
