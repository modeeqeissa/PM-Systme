import type { HTMLAttributes, ReactNode } from "react";

interface Props extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  /** tighten the default padding (p-6 → p-4) */
  compact?: boolean;
}

/** Frosted structural container — the large surfaces of a screen (a form
 *  column, a table wrapper, a section). Semi-transparent over the near-black
 *  ground with a backdrop blur. */
export function GlassPanel({ children, compact = false, className = "", ...rest }: Props) {
  return (
    <div
      className={
        "rounded-xl border border-hair bg-surface/70 backdrop-blur-panel shadow-[0_1px_0_0_rgba(255,255,255,.02)_inset] " +
        (compact ? "p-4 " : "p-6 ") +
        className
      }
      {...rest}
    >
      {children}
    </div>
  );
}
