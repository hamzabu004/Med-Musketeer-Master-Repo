import { Menu } from "lucide-react";
import type { Role } from "@/auth/roles";
import { dataSource } from "@/config/capabilities";
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
      <div className="flex items-center">
        {dataSource === "mock" && (
          <span
            className="whitespace-nowrap rounded-[var(--radius-xs)] border border-[var(--color-warning)] px-2 py-0.5 text-xs font-medium text-[var(--color-warning)]"
            title="This deployment shows sample data, not real patients."
          >
            Sample data
          </span>
        )}
        <AccountMenu role={role} />
      </div>
    </header>
  );
}
