import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Badge, GlassCard, GlassPanel, SectionLabel, Spinner } from "@pmp/ui";
import { ApiError, dashboard as dashApi } from "../../lib/api";
import { currentClaims } from "../../lib/auth";
import { currentMonthRange, monthLabel } from "../../lib/datetime";

function Stat({ value, label, tone }: { value: React.ReactNode; label: string; tone?: "bad" | "warn" }) {
  return (
    <div>
      <div
        className={
          "font-mono text-3xl font-semibold " +
          (tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : "text-ink")
        }
      >
        {value}
      </div>
      <div className="mt-1 text-xs text-ink-faint">{label}</div>
    </div>
  );
}

/** B2 — the dashboard-service read models, relocated into the Command Center in
 *  the dark style. Same fetch (dashApi.kpis) and same TanStack cache key as the
 *  standalone Station dashboard; no new API layer. */
export function LiveKpisPanel() {
  const claims = currentClaims();
  const defaults = currentMonthRange();

  const [stationId, setStationId] = useState(claims?.station_id ?? "");
  const [applied, setApplied] = useState({
    station_id: claims?.station_id ?? "",
    from: defaults.from,
    to: defaults.to,
  });

  const query = useQuery({
    queryKey: ["kpis", applied],
    queryFn: () =>
      dashApi.kpis({
        station_id: applied.station_id || undefined,
        from: applied.from || undefined,
        to: applied.to || undefined,
      }),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  const otherError =
    query.error && !forbidden && !(query.error instanceof ApiError && query.error.status === 401);

  const snap = query.data;
  const isDefaultRange = applied.from === defaults.from && applied.to === defaults.to;
  const trendRows = snap
    ? [...snap.crime_trends]
        .filter((b) => (isDefaultRange ? b.month === defaults.from : true))
        .sort((a, b) => b.count - a.count)
    : [];

  return (
    <div className="flex flex-col gap-5">
      <GlassPanel compact>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setApplied({ station_id: stationId.trim(), from: defaults.from, to: defaults.to });
          }}
          className="flex flex-wrap items-end gap-3"
        >
          <label className="flex flex-1 flex-col gap-1 text-sm">
            <span className="font-medium text-ink-muted">Station id</span>
            <input
              value={stationId}
              onChange={(e) => setStationId(e.target.value)}
              placeholder="blank = force-wide"
              className="rounded-lg border border-hair bg-surface-2 px-3 py-2 font-mono text-xs text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-accent-command/50"
            />
          </label>
          <button
            type="submit"
            className="rounded-lg bg-accent-command px-4 py-2 text-sm font-medium text-white hover:brightness-110"
          >
            Apply
          </button>
          <span className="text-xs text-ink-faint">
            {monthLabel(defaults.from)} · refreshed by the event stream, not on demand
          </span>
        </form>
      </GlassPanel>

      {query.isLoading && (
        <GlassPanel>
          <Spinner label="Loading KPIs…" />
        </GlassPanel>
      )}
      {forbidden && (
        <Alert variant="error">
          Your role can't view KPIs — needs <code>dashboard.view</code>.
        </Alert>
      )}
      {otherError && <Alert variant="error">Couldn't load KPIs: {(query.error as Error).message}</Alert>}

      {snap && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <GlassCard accent="dashboard">
            <SectionLabel>Cases</SectionLabel>
            <p className="mt-1 text-xs text-ink-faint">
              {snap.station_id ? `Station ${snap.station_id}` : "Force-wide"} · {applied.from} → {applied.to}
            </p>
            <div className="mt-4 flex flex-wrap gap-x-10 gap-y-4">
              <Stat value={snap.cases.opened} label="Open" />
              <Stat value={snap.cases.closed} label="Closed" />
              <Stat value={snap.cases.arrests_recorded} label="Arrests recorded" />
              <Stat value={snap.cases.avg_case_age_days ?? "—"} label="Avg case age (days)" />
            </div>
          </GlassCard>

          <GlassCard accent="dashboard">
            <SectionLabel>Evidence integrity</SectionLabel>
            <p className="mt-1 text-xs text-ink-faint">mv_evidence_integrity — force-wide.</p>
            <div className="mt-4 flex flex-wrap gap-x-10 gap-y-4">
              <Stat value={snap.evidence_integrity.evidence_logged} label="Evidence logged" />
              <Stat value={snap.evidence_integrity.pending_transfer_ack} label="Pending transfer ack" />
              <Stat
                value={snap.evidence_integrity.hash_mismatches}
                label="Hash mismatches"
                tone={snap.evidence_integrity.hash_mismatches > 0 ? "bad" : undefined}
              />
            </div>
          </GlassCard>

          <GlassCard accent="dashboard">
            <SectionLabel>Crime trend by type</SectionLabel>
            <p className="mt-1 text-xs text-ink-faint">
              {isDefaultRange ? monthLabel(defaults.from) : `${applied.from} → ${applied.to}`}
            </p>
            {trendRows.length === 0 ? (
              <p className="mt-4 text-sm text-ink-faint">No incidents recorded for this window.</p>
            ) : (
              <ul className="mt-4 flex flex-col gap-2">
                {trendRows.map((b) => (
                  <li
                    key={`${b.month}:${b.incident_type ?? "_"}`}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-ink">{b.incident_type ?? "(unspecified)"}</span>
                    <span className="font-mono font-medium text-ink">{b.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </GlassCard>

          <GlassCard accent="dashboard">
            <SectionLabel>Unit readiness</SectionLabel>
            <p className="mt-1 text-xs text-ink-faint">
              mv_unit_readiness (FR-DASH-02) — certification compliance and current leave per unit.
            </p>
            {snap.unit_readiness.length === 0 ? (
              <p className="mt-4 text-sm text-ink-faint">No units projected yet.</p>
            ) : (
              <table className="mt-4 w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wide text-ink-faint">
                    <th className="pb-2 font-medium">Unit</th>
                    <th className="pb-2 text-right font-medium">Officers</th>
                    <th className="pb-2 text-right font-medium">Certified</th>
                    <th className="pb-2 text-right font-medium">On leave</th>
                  </tr>
                </thead>
                <tbody>
                  {[...snap.unit_readiness]
                    .sort((a, b) => (a.unit_name ?? a.unit_id).localeCompare(b.unit_name ?? b.unit_id))
                    .map((u) => (
                      <tr key={u.unit_id} className="border-t border-hair">
                        <td className="py-2 text-ink">{u.unit_name ?? u.unit_id.slice(0, 8)}</td>
                        <td className="py-2 text-right font-mono text-ink">{u.total_officers}</td>
                        <td className="py-2 text-right font-mono text-ink">
                          {u.certified_officer_pct === null ? "—" : `${u.certified_officer_pct.toFixed(0)}%`}
                        </td>
                        <td
                          className={
                            "py-2 text-right font-mono " +
                            (u.on_leave_count > 0 ? "text-warn" : "text-ink")
                          }
                        >
                          {u.on_leave_count}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
          </GlassCard>
        </div>
      )}

      {snap && (
        <p className="text-[11px] text-ink-faint">
          <Badge tone="info">read-only</Badge> Same projection the Station dashboard shows
          (FR-DASH-01/02/03); gated on <code>dashboard.view</code>.
        </p>
      )}
    </div>
  );
}
