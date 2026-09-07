import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
}

const base =
  "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm " +
  "font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 " +
  "focus:ring-offset-bg disabled:cursor-not-allowed disabled:opacity-60";

const styles: Record<Variant, string> = {
  primary:
    "bg-accent-command text-white hover:brightness-110 focus:ring-accent-command",
  secondary:
    "border border-hair bg-surface-2 text-ink hover:bg-surface-3 focus:ring-ink-faint",
  danger: "bg-bad text-white hover:brightness-110 focus:ring-bad",
  ghost:
    "text-ink-muted hover:bg-surface-2 hover:text-ink focus:ring-ink-faint",
};

export function Button({
  variant = "primary",
  loading = false,
  disabled,
  children,
  className = "",
  ...rest
}: Props) {
  return (
    <button
      className={`${base} ${styles[variant]} ${className}`}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden
          className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
}
