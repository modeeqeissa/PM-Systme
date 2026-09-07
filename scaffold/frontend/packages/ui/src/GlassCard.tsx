import type { HTMLAttributes, ReactNode } from "react";

export type Accent =
  | "command"
  | "hr"
  | "dashboard"
  | "community"
  | "cases"
  | "training";

/** full class strings so Tailwind's JIT sees them */
const BAR: Record<Accent, string> = {
  command: "bg-accent-command",
  hr: "bg-accent-hr",
  dashboard: "bg-accent-dashboard",
  community: "bg-accent-community",
  cases: "bg-accent-cases",
  training: "bg-accent-training",
};
const HOVER_BORDER: Record<Accent, string> = {
  command: "hover:border-accent-command/60",
  hr: "hover:border-accent-hr/60",
  dashboard: "hover:border-accent-dashboard/60",
  community: "hover:border-accent-community/60",
  cases: "hover:border-accent-cases/60",
  training: "hover:border-accent-training/60",
};

interface Props extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  /** paints a 3px top bar and tints the hover border */
  accent?: Accent;
  /** adds the hover-lift + pointer affordance (use when the whole card is clickable) */
  interactive?: boolean;
  compact?: boolean;
}

/** A content card on the frosted surface. Optional accent bar per functional
 *  area; subtle hover-lift when interactive. */
export function GlassCard({
  children,
  accent,
  interactive = false,
  compact = false,
  className = "",
  ...rest
}: Props) {
  return (
    <div
      className={
        "relative overflow-hidden rounded-xl border border-hair bg-surface/80 " +
        (compact ? "p-4 " : "p-5 ") +
        "transition-[transform,border-color] duration-150 " +
        (interactive
          ? "cursor-pointer hover:-translate-y-0.5 " + (accent ? HOVER_BORDER[accent] : "hover:border-ink-faint")
          : "") +
        " " +
        className
      }
      {...rest}
    >
      {accent && <span aria-hidden className={`absolute inset-x-0 top-0 h-[3px] ${BAR[accent]}`} />}
      {children}
    </div>
  );
}
