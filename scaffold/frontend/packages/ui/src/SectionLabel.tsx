import type { ReactNode } from "react";

/** Uppercase, wide-tracked group heading — matches the reference shell's
 *  section dividers ("Operational Environments", "Entities & Records"). */
export function SectionLabel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={
        "text-[11px] font-bold uppercase tracking-[0.08em] text-ink-faint " + className
      }
    >
      {children}
    </div>
  );
}
