import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Badge, GlassCard, GlassPanel, SectionLabel, Spinner } from "@pmp/ui";
import { ApiError, integration as intApi, type IntegrationConfig } from "../../lib/api";
import { hasPerm } from "../../lib/rbac";

/** B5 — integration-gateway control. View integration_configs and recent
 *  external_system_logs (integration.read); flip each system's kill switch
 *  (PATCH /integration-configs/{id}, integration.write — emits
 *  IntegrationConfigUpdated, audited). */
export function IntegrationControlPanel() {
  const qc = useQueryClient();
  const canWrite = hasPerm("integration.write");
  const [banner, setBanner] = useState<{ kind: "success" | "error" | "warn"; text: string } | null>(null);
  const [logSystem, setLogSystem] = useState("");

  const configsQ = useQuery({
    queryKey: ["int-configs"],
    queryFn: () => intApi.configs(),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });
  const logsQ = useQuery({
    queryKey: ["int-logs", logSystem],
    queryFn: () => intApi.logs({ system_name: logSystem || undefined }),
    retry: (n, err) => !(err instanceof ApiError) && n < 2,
  });

  const toggle = useMutation({
    mutationFn: (c: IntegrationConfig) => intApi.setEnabled(c.id, !c.enabled),
    onSuccess: (updated) => {
      setBanner({
        kind: updated.enabled ? "success" : "warn",
        text: updated.enabled
          ? `${updated.system_name} re-enabled — adapter calls will go through. Audit event emitted.`
          : `${updated.system_name} kill switch ON — adapter calls now 409 until re-enabled. Audit event emitted.`,
      });
      qc.invalidateQueries({ queryKey: ["int-configs"] });
    },
    onError: (e) => setBanner({ kind: "error", text: msg(e) }),
  });

  const forbidden = configsQ.error instanceof ApiError && configsQ.error.status === 403;
  const otherError =
    configsQ.error && !forbidden && !(configsQ.error instanceof ApiError && configsQ.error.status === 401);
  const configs = configsQ.data ?? [];
  const logs = logsQ.data ?? [];

  return (
    <div className="flex flex-col gap-5">
      {banner && (
        <Alert variant={banner.kind === "success" ? "success" : banner.kind === "warn" ? "warn" : "error"}>
          {banner.text}
        </Alert>
      )}

      {forbidden && (
        <Alert variant="error">
          Your role can't view integration config — needs <code>integration.read</code>.
        </Alert>
      )}
      {otherError && (
        <Alert variant="error">Couldn't reach integration-gateway: {(configsQ.error as Error).message}</Alert>
      )}

      <div>
        <SectionLabel>External systems · kill switch</SectionLabel>
        <p className="mt-1 text-xs text-ink-faint">
          {canWrite
            ? "Turning a system off makes its adapter calls 409 immediately (docs §9.3.9)."
            : "Read-only — flipping a switch needs integration.write."}
        </p>
        {configsQ.isLoading ? (
          <div className="mt-3">
            <Spinner label="Loading integration config…" />
          </div>
        ) : configs.length === 0 && !forbidden && !otherError ? (
          <p className="mt-3 text-sm text-ink-faint">No integration systems configured.</p>
        ) : (
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {configs.map((c) => (
              <GlassCard key={c.id} accent="command" compact>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-mono text-sm text-ink">{c.system_name}</div>
                    <div className="mt-1">
                      <Badge tone={c.enabled ? "ok" : "bad"}>{c.enabled ? "enabled" : "killed"}</Badge>
                    </div>
                  </div>
                  <button
                    onClick={() => toggle.mutate(c)}
                    disabled={!canWrite || (toggle.isPending && toggle.variables?.id === c.id)}
                    className={
                      "rounded-lg border px-3 py-1.5 text-xs font-medium disabled:opacity-50 " +
                      (c.enabled
                        ? "border-bad/40 text-bad hover:bg-bad/10"
                        : "border-ok/40 text-ok hover:bg-ok/10")
                    }
                  >
                    {toggle.isPending && toggle.variables?.id === c.id
                      ? "…"
                      : c.enabled
                        ? "Kill"
                        : "Re-enable"}
                  </button>
                </div>
              </GlassCard>
            ))}
          </div>
        )}
      </div>

      <GlassPanel compact>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <SectionLabel>external_system_logs · newest first{logsQ.isFetching ? " · loading…" : ""}</SectionLabel>
          <label className="flex items-center gap-2 text-xs text-ink-faint">
            system
            <select
              value={logSystem}
              onChange={(e) => setLogSystem(e.target.value)}
              className="rounded border border-hair bg-surface-2 px-2 py-1 text-ink"
            >
              <option value="">all</option>
              {configs.map((c) => (
                <option key={c.id} value={c.system_name}>
                  {c.system_name}
                </option>
              ))}
            </select>
          </label>
        </div>
        {logsQ.isLoading ? (
          <Spinner label="Loading logs…" />
        ) : logs.length === 0 ? (
          <p className="text-sm text-ink-faint">No external-system calls logged yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="border-b border-hair text-xs uppercase tracking-wide text-ink-faint">
                <tr>
                  <th className="py-2 pr-3 font-medium">#</th>
                  <th className="py-2 pr-3 font-medium">System</th>
                  <th className="py-2 pr-3 font-medium">Direction</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">Correlation</th>
                </tr>
              </thead>
              <tbody>
                {[...logs]
                  .sort((a, b) => b.id - a.id)
                  .map((l) => (
                    <tr key={l.id} className="border-b border-hair/60 last:border-0">
                      <td className="py-2 pr-3 font-mono text-xs text-ink-faint">{l.id}</td>
                      <td className="py-2 pr-3 font-mono text-xs text-ink">{l.system_name}</td>
                      <td className="py-2 pr-3 text-xs text-ink-muted">{l.direction}</td>
                      <td className="py-2 pr-3">
                        <Badge
                          tone={
                            l.response_status == null
                              ? "neutral"
                              : l.response_status < 400
                                ? "ok"
                                : l.response_status === 409
                                  ? "warn"
                                  : "bad"
                          }
                        >
                          {l.response_status ?? "—"}
                        </Badge>
                      </td>
                      <td className="py-2 pr-3 font-mono text-[11px] text-ink-faint">
                        {l.correlation_id.slice(0, 8)}…
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </GlassPanel>
    </div>
  );
}

function msg(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 403) return "Forbidden — flipping a kill switch needs integration.write.";
    return e.message;
  }
  return (e as Error)?.message ?? "Request failed";
}
