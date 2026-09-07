import type { ReactNode } from "react";

/** Plain content panel on the dark ground. For the frosted / accented
 *  variants use GlassPanel / GlassCard. */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-hair bg-surface p-6 ${className}`}>
      {children}
    </div>
  );
}
