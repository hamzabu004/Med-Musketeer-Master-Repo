import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

/** A bordered table that scrolls sideways inside its own box on narrow screens, never the page.
 * `relative`: absolutely positioned content (screen-reader text) stays inside the scrolling box;
 * without it, it escapes and widens the page, and phones zoom out to fit. */
export function Table({ label, minWidth = 720, children }: { label: string; minWidth?: number; children: React.ReactNode }) {
  return (
    <div className="relative overflow-x-auto rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)]">
      <table className="w-full border-collapse text-sm" style={{ minWidth }} aria-label={label}>
        {children}
      </table>
    </div>
  );
}

export function THead({ columns }: { columns: string[] }) {
  return (
    <thead className="bg-[var(--color-surface-subtle)] text-left text-[var(--color-text-muted)]">
      <tr>
        {columns.map((column) => (
          <th key={column} scope="col" className="px-3 py-2 font-medium">
            {column}
          </th>
        ))}
      </tr>
    </thead>
  );
}

export function Tr({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("border-t border-[var(--color-border)] align-top", className)} {...props} />;
}

export function Td({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-3 py-2.5", className)} {...props} />;
}

export function Th({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th className={cn("px-3 py-2.5 text-left font-medium", className)} {...props} />;
}
