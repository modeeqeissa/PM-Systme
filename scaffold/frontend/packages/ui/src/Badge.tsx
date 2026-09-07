import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "ok" | "warn" | "bad" | "info";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-hair bg-surface-2 text-ink-muted",
  ok: "border-ok/30 bg-ok/10 text-ok",
  warn: "border-warn/30 bg-warn/10 text-warn",
  bad: "border-bad/30 bg-bad/10 text-bad",
  info: "border-accent-command/30 bg-accent-command/10 text-accent-command",
};

interface Props {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}

/** Small status pill — case status, MFA on/off, health, etc. */
export function Badge({ children, tone = "neutral", className = "" }: Props) {
  return (
    <span
      className={
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium " +
        TONES[tone] +
        " " +
        className
      }
    >
      {children}
    </span>
  );
}
