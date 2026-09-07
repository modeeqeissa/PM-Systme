import type { ReactNode } from "react";

type Variant = "error" | "info" | "success" | "warn";

const styles: Record<Variant, string> = {
  error: "border-bad/30 bg-bad/10 text-bad",
  info: "border-hair bg-surface-2 text-ink-muted",
  success: "border-ok/30 bg-ok/10 text-ok",
  warn: "border-warn/30 bg-warn/10 text-warn",
};

interface Props {
  variant?: Variant;
  children: ReactNode;
}

export function Alert({ variant = "info", children }: Props) {
  return (
    <div
      role={variant === "error" ? "alert" : "status"}
      className={`rounded-lg border px-3 py-2 text-sm ${styles[variant]}`}
    >
      {children}
    </div>
  );
}
