import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Spinner, TextInput } from "@pmp/ui";
import { ApiError, dashboard as dashApi } from "../lib/api";
import { currentClaims } from "../lib/auth";
import { currentMonthRange, monthLabel } from "../lib/datetime";

export function DashboardPage() {
  const navigate = useNavigate();
  const claims = currentClaims();
  const defaults = currentMonthRange();

  // filters (endpoint supports station_id + from/to)
  const [stationId, setStationId] = useState(claims?.station_id ?? "");
  const [from, setFrom] = useState(defaults.from);
  const [to, setTo] = useState(defaults.to);
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

  useEffect(() => {
    if (query.error instanceof ApiError && query.error.status === 401) {
      navigate("/login", { replace: true });
    }
  }, [query.error, navigate]);

  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  const otherError =
    query.error &&
    !forbidden &&
    !(query.error instanceof ApiError && query.error.status === 401);

  const snap = query.data;
  const monthBuckets = snap
    ? [...snap.crime_trends]
        .filter((b) => b.month === defaults.from) // current month's first-of-month key
        .sort((a, b) => b.count - a.count)
    : [];
  // if the applied range isn't the default current month, just show every bucket
  const trendRows =
    applied.from === defaults.from && applied.to === defaults.to
      ? monthBuckets
      : snap
        ? [...snap.crime_trends].sort((a, b) => b.count - a.count)
        : [];

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Station dashboard</h1>
          <p className="text-sm text-slate-500">
            Read models from dashboard-service (FR-DASH-01/02/03) — refreshed by the
            domain-event stream, not on demand.
          </p>
        </div>
        <Link to="/cases" className="text-sm text-slate-500 underline">
          Cases
        </Link>
      </div>

      <Card className="mb-6">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setApplied({ station_id: stationId.trim(), from, to });
          }}
          className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_auto_auto_auto]"
        >
          <TextInput
            label="Station id"
            value={stationId}
            onChange={(e) => setStationId(e.target.value)}
            hint="Defaults to your station; blank = force-wide."
          />
          <div className="flex flex-col gap-1">
            <label htmlFor="from" className="text-sm font-medium text-slate-700">
              From
            </label>
            <input
              id="from"
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="to" className="text-sm font-medium text-slate-700">
              To
            </label>
            <input
              id="to"
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
            />
          </div>
          <div className="flex items-end">
            <Button type="submit" loading={query.isFetching}>
              Apply
            </Button>
          </div>
        </form>
      </Card>

      {query.isLoading && (
        <Card>
          <Spinner label="Loading KPIs…" />
        </Card>
      )}

      {forbidden && (
        <Alert variant="error">
          Your role can't view the dashboard. This needs the <code>dashboard.view</code>{" "}
          permission.
        </Alert>
      )}
      {otherError && (
        <Alert variant="error">
          Couldn't load KPIs: {(query.error as Error).message}
        </Alert>
      )}

      {snap && (
        <div className="flex flex-col gap-6">
          <Card>
            <h2 className="mb-1 text-sm font-medium uppercase tracking-wide text-slate-500">
              Cases
            </h2>
            <p className="mb-4 text-xs text-slate-500">
              {snap.station_id ? `Station ${snap.station_id}` : "Force-wide (all stations)"}
              {" · "}
              {applied.from} → {applied.to}
            </p>
            <div className="flex gap-10">
              <div>
                <div className="text-3xl font-semibold text-slate-900">
                  {snap.cases.opened}
                </div>
                <div className="text-sm text-slate-500">Open</div>
              </div>
              <div>
                <div className="text-3xl font-semibold text-slate-900">
                  {snap.cases.closed}
                </div>
                <div className="text-sm text-slate-500">Closed</div>
              </div>
              <div>
                <div className="text-3xl font-semibold text-slate-900">
                  {snap.cases.arrests_recorded}
                </div>
                <div className="text-sm text-slate-500">Arrests recorded</div>
              </div>
              <div>
                <div className="text-3xl font-semibold text-slate-900">
                  {snap.cases.avg_case_age_days ?? "—"}
                </div>
                <div className="text-sm text-slate-500">Avg case age (days)</div>
              </div>
            </div>
          </Card>

          <Card>
            <h2 className="mb-1 text-sm font-medium uppercase tracking-wide text-slate-500">
              Crime trend by type
            </h2>
            <p className="mb-4 text-xs text-slate-500">
              {applied.from === defaults.from && applied.to === defaults.to
                ? monthLabel(defaults.from)
                : `${applied.from} → ${applied.to}`}
            </p>
            {trendRows.length === 0 ? (
              <p className="text-sm text-slate-500">No incidents recorded for this window.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {trendRows.map((b) => (
                  <li
                    key={`${b.month}:${b.incident_type ?? "_"}`}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-slate-800">
                      {b.incident_type ?? "(unspecified)"}
                    </span>
                    <span className="font-mono font-medium text-slate-900">{b.count}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <h2 className="mb-1 text-sm font-medium uppercase tracking-wide text-slate-500">
              Evidence integrity
            </h2>
            <p className="mb-4 text-xs text-slate-500">
              mv_evidence_integrity — force-wide (no station key on this projection).
            </p>
            <div className="flex gap-10">
              <div>
                <div className="text-3xl font-semibold text-slate-900">
                  {snap.evidence_integrity.evidence_logged}
                </div>
                <div className="text-sm text-slate-500">Evidence logged</div>
              </div>
              <div>
                <div className="text-3xl font-semibold text-slate-900">
                  {snap.evidence_integrity.pending_transfer_ack}
                </div>
                <div className="text-sm text-slate-500">Pending transfer ack</div>
              </div>
              <div>
                <div
                  className={`text-3xl font-semibold ${
                    snap.evidence_integrity.hash_mismatches > 0
                      ? "text-rose-600"
                      : "text-slate-900"
                  }`}
                >
                  {snap.evidence_integrity.hash_mismatches}
                </div>
                <div className="text-sm text-slate-500">Hash mismatches</div>
              </div>
            </div>
          </Card>

          <p className="text-xs text-slate-400">
            mv_unit_readiness is intentionally not shown — hr-service / training-service
            aren't built yet, so it has no data to project.
          </p>
        </div>
      )}
    </div>
  );
}
