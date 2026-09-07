import { Badge, GlassCard, GlassPanel, SectionLabel, StatusPulse } from "@pmp/ui";
import type { PulseStatus } from "@pmp/ui";
import { HEALTH_LAYERS } from "./services";
import { useHealth, type ServiceHealth } from "./useHealth";

const PULSE: Record<ServiceHealth["state"], PulseStatus> = {
  up: "ok",
  down: "bad",
  checking: "idle",
};

function relative(ts: number | null): string {
  if (ts == null) return "—";
  const s = Math.round((Date.now() - ts) / 1000);
  if (s < 2) return "just now";
  if (s < 60) return `${s}s ago`;
  return `${Math.round(s / 60)}m ago`;
}

export function SystemHealthPanel() {
  const { health, lastSweep, refresh } = useHealth(5000);

  const flat = Object.values(health);
  const up = flat.filter((h) => h.state === "up").length;
  const down = flat.filter((h) => h.state === "down").length;
  const total = flat.length;

  return (
    <div className="flex flex-col gap-5">
      <GlassPanel compact>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-4">
            <StatusPulse
              status={down > 0 ? "bad" : up === total ? "ok" : "warn"}
              label={
                down > 0
                  ? `${down} service${down > 1 ? "s" : ""} down`
                  : up === total
                    ? `all ${total} services up`
                    : `${up} / ${total} up`
              }
            />
            <span className="text-xs text-ink-faint">
              polled every 5s · last sweep {relative(lastSweep)}
            </span>
          </div>
          <button
            onClick={() => void refresh()}
            className="rounded-lg border border-hair bg-surface-2 px-3 py-1.5 text-xs font-medium text-ink-muted hover:bg-surface-3"
          >
            Refresh now
          </button>
        </div>
      </GlassPanel>

      {HEALTH_LAYERS.map((layer, i) => (
        <div key={layer.id} className="relative">
          {i > 0 && (
            <div
              aria-hidden
              className="mx-auto mb-4 h-4 w-px bg-gradient-to-b from-hair to-transparent"
            />
          )}
          <div className="mb-2 flex items-baseline gap-3">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-surface-2 font-mono text-xs text-ink-faint">
              {i + 1}
            </span>
            <SectionLabel>{layer.title}</SectionLabel>
            <span className="text-xs text-ink-faint">{layer.blurb}</span>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {layer.services.map((svc) => {
              const h = health[svc.key];
              return (
                <GlassCard key={svc.key} compact>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2 font-mono text-sm text-ink">
                        <StatusPulse status={PULSE[h.state]} animate={h.state === "up"} />
                        {svc.name}
                      </div>
                      <div className="mt-1 font-mono text-[11px] text-ink-faint">
                        :{svc.port} · {svc.note}
                      </div>
                    </div>
                    <Badge
                      tone={h.state === "up" ? "ok" : h.state === "down" ? "bad" : "neutral"}
                    >
                      {h.state === "checking" ? "…" : h.state}
                    </Badge>
                  </div>
                  <div className="mt-3 flex items-center justify-between text-[11px] text-ink-faint">
                    <span>{h.detail ?? "—"}</span>
                    <span className="font-mono">
                      {h.latencyMs != null ? `${h.latencyMs} ms` : ""}
                    </span>
                  </div>
                </GlassCard>
              );
            })}
          </div>
        </div>
      ))}

      <p className="text-[11px] leading-relaxed text-ink-faint">
        Each pulse is a live poll of that service's <code className="font-mono">/health</code>{" "}
        through the dev proxy — green = 200, red = non-200 / unreachable / &gt;4s.
        <code className="font-mono"> /health</code> is a static liveness check, so there is no
        "degraded" state to show. The API gateway (§3.5) and the data plane (Postgres / Kafka /
        MinIO) aren't reachable from the browser and aren't probed here.
      </p>
    </div>
  );
}
