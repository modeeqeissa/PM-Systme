import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
}

const base =
  "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm " +
  "font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1 " +
  "disabled:cursor-not-allowed disabled:opacity-60";

const styles: Record<Variant, string> = {
  primary: "bg-slate-900 text-white hover:bg-slate-700 focus:ring-slate-500",
  secondary:
    "bg-white text-slate-900 border border-slate-300 hover:bg-slate-50 focus:ring-slate-400",
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
