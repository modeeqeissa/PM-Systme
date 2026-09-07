import { useCallback, useEffect, useRef, useState } from "react";
import { ALL_SERVICES } from "./services";

export type HealthState = "up" | "down" | "checking";

export interface ServiceHealth {
  state: HealthState;
  latencyMs: number | null;
  checkedAt: number | null;
  detail: string | null;
}

const BLANK: ServiceHealth = { state: "checking", latencyMs: null, checkedAt: null, detail: null };

async function probe(proxy: string): Promise<ServiceHealth> {
  const started = performance.now();
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 4000);
    const res = await fetch(`${proxy}/health`, { signal: ctl.signal, cache: "no-store" });
    clearTimeout(t);
    const latencyMs = Math.round(performance.now() - started);
    if (!res.ok) {
      return { state: "down", latencyMs, checkedAt: Date.now(), detail: `HTTP ${res.status}` };
    }
    const body = (await res.json().catch(() => null)) as { status?: string; service?: string } | null;
    // /health is a static liveness check ({status:"ok"}) — it can't report
    // "degraded", so this is up/down only.
    return {
      state: "up",
      latencyMs,
      checkedAt: Date.now(),
      detail: body?.status ? `status: ${body.status}` : null,
    };
  } catch (e) {
    return {
      state: "down",
      latencyMs: null,
      checkedAt: Date.now(),
      detail: e instanceof DOMException && e.name === "AbortError" ? "timeout (>4s)" : "unreachable",
    };
  }
}

/** Polls every service's /health on an interval. Returns the map plus a manual
 *  refresh and the timestamp of the last full sweep. */
export function useHealth(intervalMs = 5000) {
  const [health, setHealth] = useState<Record<string, ServiceHealth>>(() =>
    Object.fromEntries(ALL_SERVICES.map((s) => [s.key, BLANK])),
  );
  const [lastSweep, setLastSweep] = useState<number | null>(null);
  const running = useRef(false);

  const sweep = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    try {
      const results = await Promise.all(
        ALL_SERVICES.map(async (s) => [s.key, await probe(s.proxy)] as const),
      );
      setHealth((prev) => ({ ...prev, ...Object.fromEntries(results) }));
      setLastSweep(Date.now());
    } finally {
      running.current = false;
    }
  }, []);

  useEffect(() => {
    void sweep();
    const id = setInterval(() => void sweep(), intervalMs);
    return () => clearInterval(id);
  }, [sweep, intervalMs]);

  return { health, lastSweep, refresh: sweep };
}
