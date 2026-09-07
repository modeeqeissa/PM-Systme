import { useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { Alert, Badge, GlassPanel, SectionLabel, Spinner } from "@pmp/ui";
import type { BadgeTone } from "@pmp/ui";
import { ApiError, audit as auditApi, type AuditAction, type AuditQuery } from "../../lib/api";
import { ALL_SERVICES } from "./services";

const ACTIONS: AuditAction[] = ["create", "read", "update", "delete", "export"];
const ACTION_TONE: Record<AuditAction, BadgeTone> = {
  create: "ok",
  read: "neutral",
  update: "info",
  delete: "bad",
  export: "warn",
};
const PAGE_SIZES = [25, 50, 100];

type Filters = {
  service_name: string;
  action: string;
  entity_type: string;
  entity_id: string;
  actor_id: string;
  from: string;
  to: string;
};
const EMPTY: Filters = {
  service_name: "",
  action: "",
  entity_type: "",
  entity_id: "",
  actor_id: "",
  from: "",
  to: "",
};

function toQuery(f: Filters, limit: number, offset: number): AuditQuery {
  return {
    service_name: f.service_name || undefined,
    action: f.action || undefined,
    entity_type: f.entity_type || undefined,
    entity_id: f.entity_id || undefined,
    actor_id: f.actor_id || undefined,
    from: f.from ? new Date(f.from).toISOString() : undefined,
    to: f.to ? new Date(f.to).toISOString() : undefined,
    limit,
    offset,
  };
}

/** B3 — the real oversight view over audit-service's hash-chained log
 *  (GET /audit, gated on audit.read). Filter by service / actor / entity /
 *  action / time; offset-paginated. */
export function AuditFeedPanel() {
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [applied, setApplied] = useState<Filters>(EMPTY);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);

  const query = useQuery({
    queryKey: ["audit", applied, limit, offset],
    queryFn: () => auditApi.query(toQuery(applied, limit, offset)),
    placeholderData: keepPreviousData,
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  const otherError =
    query.error && !forbidden && !(query.error instanceof ApiError && query.error.status === 401);
  const rows = query.data ?? [];
  const set = (k: keyof Filters, v: string) => setDraft((d) => ({ ...d, [k]: v }));

  return (
    <div className="flex flex-col gap-5">
      <GlassPanel compact>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setOffset(0);
            setApplied(draft);
          }}
          className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
        >
          <Field label="Service">
            <select
              value={draft.service_name}
              onChange={(e) => set("service_name", e.target.value)}
              className={inputCls}
            >
              <option value="">any</option>
              {ALL_SERVICES.map((s) => (
                <option key={s.key} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Action">
            <select value={draft.action} onChange={(e) => set("action", e.target.value)} className={inputCls}>
              <option value="">any</option>
              {ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Entity type">
            <input
              value={draft.entity_type}
              onChange={(e) => set("entity_type", e.target.value)}
              placeholder="e.g. case, evidence_item"
              className={inputCls}
            />
          </Field>
          <Field label="Entity id">
            <input
              value={draft.entity_id}
              onChange={(e) => set("entity_id", e.target.value)}
              placeholder="exact id"
              className={inputCls + " font-mono text-xs"}
            />
          </Field>
          <Field label="Actor id">
            <input
              value={draft.actor_id}
              onChange={(e) => set("actor_id", e.target.value)}
              placeholder="user uuid"
              className={inputCls + " font-mono text-xs"}
            />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="From">
              <input
                type="datetime-local"
                value={draft.from}
                onChange={(e) => set("from", e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label="To">
              <input
                type="datetime-local"
                value={draft.to}
                onChange={(e) => set("to", e.target.value)}
                className={inputCls}
              />
            </Field>
          </div>
          <div className="flex items-end gap-2">
            <button
              type="submit"
              className="rounded-lg bg-accent-command px-4 py-2 text-sm font-medium text-white hover:brightness-110"
            >
              Apply
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(EMPTY);
                setApplied(EMPTY);
                setOffset(0);
              }}
              className="rounded-lg border border-hair bg-surface-2 px-3 py-2 text-sm text-ink-muted hover:bg-surface-3"
            >
              Clear
            </button>
          </div>
        </form>
      </GlassPanel>

      {forbidden && (
        <Alert variant="error">
          Your role can't read the audit log — needs <code>audit.read</code>.
        </Alert>
      )}
      {otherError && <Alert variant="error">Couldn't load the audit log: {(query.error as Error).message}</Alert>}

      <GlassPanel compact>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <SectionLabel>
            audit_db.audit_logs · newest first{query.isFetching ? " · loading…" : ""}
          </SectionLabel>
          <div className="flex items-center gap-3 text-xs text-ink-faint">
            <label className="flex items-center gap-1">
              page size
              <select
                value={limit}
                onChange={(e) => {
                  setLimit(Number(e.target.value));
                  setOffset(0);
                }}
                className="rounded border border-hair bg-surface-2 px-1.5 py-1 text-ink"
              >
                {PAGE_SIZES.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={() => setOffset((o) => Math.max(0, o - limit))}
              disabled={offset === 0}
              className="rounded border border-hair px-2 py-1 disabled:opacity-40"
            >
              ← prev
            </button>
            <span className="font-mono">{offset + 1}–{offset + rows.length}</span>
            <button
              onClick={() => setOffset((o) => o + limit)}
              disabled={rows.length < limit}
              className="rounded border border-hair px-2 py-1 disabled:opacity-40"
            >
              next →
            </button>
          </div>
        </div>

        {query.isLoading ? (
          <Spinner label="Loading audit entries…" />
        ) : rows.length === 0 ? (
          <p className="text-sm text-ink-faint">No audit entries match these filters.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead className="border-b border-hair text-xs uppercase tracking-wide text-ink-faint">
                <tr>
                  <th className="py-2 pr-3 font-medium">#</th>
                  <th className="py-2 pr-3 font-medium">Time (UTC)</th>
                  <th className="py-2 pr-3 font-medium">Service</th>
                  <th className="py-2 pr-3 font-medium">Action</th>
                  <th className="py-2 pr-3 font-medium">Entity</th>
                  <th className="py-2 pr-3 font-medium">Actor</th>
                  <th className="py-2 pr-3 font-medium">Record hash</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-hair/60 last:border-0 align-top">
                    <td className="py-2 pr-3 font-mono text-xs text-ink-faint">{r.id}</td>
                    <td className="py-2 pr-3 font-mono text-xs text-ink-muted">
                      {r.timestamp.replace("T", " ").replace(/\.\d+.*/, "").replace("Z", "")}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs text-ink">{r.service_name}</td>
                    <td className="py-2 pr-3">
                      <Badge tone={ACTION_TONE[r.action] ?? "neutral"}>{r.action}</Badge>
                    </td>
                    <td className="py-2 pr-3">
                      <span className="text-ink">{r.entity_type}</span>
                      <span className="ml-1 font-mono text-xs text-ink-faint">
                        {r.entity_id.length > 14 ? `${r.entity_id.slice(0, 8)}…` : r.entity_id}
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-xs">
                      <span className="text-ink-muted">{r.actor_role || "—"}</span>
                      <span className="ml-1 font-mono text-ink-faint">{r.actor_id.slice(0, 8)}…</span>
                    </td>
                    <td className="py-2 pr-3 font-mono text-[11px] text-ink-faint">
                      {r.record_hash.slice(0, 12)}…
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-[11px] text-ink-faint">
          Hash-chained, append-only (FR-AUD-01/02). Each row's <code>record_hash</code> links to the
          previous — run <code>GET /audit/verify</code> to check chain integrity.
        </p>
      </GlassPanel>
    </div>
  );
}

const inputCls =
  "w-full rounded-lg border border-hair bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-accent-command/50";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">{label}</span>
      {children}
    </label>
  );
}
