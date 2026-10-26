import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "danger";

export function Button({
  className,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const variants: Record<Variant, string> = {
    primary: "border border-[var(--color-brand)] bg-[var(--color-brand)] text-[var(--color-on-brand)] hover:bg-[var(--color-brand-strong)]",
    secondary: "border border-[var(--color-border-strong)] bg-[var(--color-surface)] text-[var(--color-text)] hover:bg-[var(--color-surface-subtle)]",
    danger: "border border-[var(--color-critical)] bg-[var(--color-critical)] text-[var(--color-on-brand)]",
  };

  return (
    <button
      className={cn(
        "inline-flex h-9 items-center justify-center gap-2 rounded-[var(--radius-sm)] px-3 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
