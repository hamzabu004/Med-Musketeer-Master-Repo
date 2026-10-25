import type { SelectHTMLAttributes } from "react";

export function LabeledSelect({
  label,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string }) {
  return (
    <label className="block text-sm font-medium">
      {label}
      <select
        className="mt-1 h-9 w-full min-w-36 rounded-[var(--radius-sm)] border border-[var(--color-border-strong)] bg-[var(--color-surface)] px-2 text-sm"
        {...props}
      >
        {children}
      </select>
    </label>
  );
}
