import type { ReactNode } from "react";

interface Props {
  variant?: "error" | "info";
  children: ReactNode;
}

const styles = {
  error: "border-red-300 bg-red-50 text-red-800",
  info: "border-slate-300 bg-slate-50 text-slate-700",
};

export function Alert({ variant = "info", children }: Props) {
  return (
    <div
      role={variant === "error" ? "alert" : "status"}
      className={`rounded-md border px-3 py-2 text-sm ${styles[variant]}`}
    >
      {children}
    </div>
  );
}
