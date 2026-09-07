import type { HTMLAttributes } from "react";

export type PulseStatus = "ok" | "warn" | "bad" | "idle";

const CORE: Record<PulseStatus, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  bad: "bg-bad",
  idle: "bg-ink-faint",
};

const RING: Record<PulseStatus, string> = {
  ok: "rgba(52,211,153,.55)",
  warn: "rgba(251,191,36,.55)",
  bad: "rgba(248,113,113,.55)",
  idle: "rgba(0,0,0,0)",
};

interface Props extends HTMLAttributes<HTMLSpanElement> {
  status: PulseStatus;
  /** show the pulsing ring animation (live states only) */
  animate?: boolean;
  label?: string;
}

/** A coloured status dot with an optional expanding-ring pulse — for live
 *  service health, active/degraded/down states. Mirrors the reference shell. */
export function StatusPulse({ status, animate = true, label, className = "", ...rest }: Props) {
  const dot = (
    <span
      aria-hidden
      className={`inline-block h-2 w-2 shrink-0 rounded-full ${CORE[status]} ${
        animate && status !== "idle" ? "animate-pmp-pulse" : ""
      }`}
      style={{ ["--pmp-pulse-ring" as string]: RING[status] }}
    />
  );
  if (!label) {
    return (
      <span className={`inline-flex ${className}`} {...rest}>
        {dot}
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center gap-2 text-xs font-medium text-ink-muted ${className}`}
      {...rest}
    >
      {dot}
      {label}
    </span>
  );
}
