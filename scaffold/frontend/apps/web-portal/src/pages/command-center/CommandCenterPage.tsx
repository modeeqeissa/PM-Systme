import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { StatusPulse } from "@pmp/ui";
import { NavBar } from "../../components/NavBar";
import { hasAnyPerm } from "../../lib/rbac";
import { PermissionNotice } from "../../routes/RequirePermission";
import { SystemHealthPanel } from "./SystemHealthPanel";
import { LiveKpisPanel } from "./LiveKpisPanel";
import { AuditFeedPanel } from "./AuditFeedPanel";
import { UserAdminPanel } from "./UserAdminPanel";
import { IntegrationControlPanel } from "./IntegrationControlPanel";
import { TAB_META } from "./tabs";

export { COMMAND_CENTER_PERMS } from "./tabs";

const RENDERERS: Record<string, () => JSX.Element> = {
  health: () => <SystemHealthPanel />,
  kpis: () => <LiveKpisPanel />,
  audit: () => <AuditFeedPanel />,
  users: () => <UserAdminPanel />,
  integration: () => <IntegrationControlPanel />,
};

export function CommandCenterPage() {
  const [params, setParams] = useSearchParams();

  const visibleTabs = useMemo(
    () => TAB_META.filter((t) => t.anyOf.length === 0 || hasAnyPerm(t.anyOf)),
    [],
  );

  const requested = params.get("tab");
  const active = TAB_META.find((t) => t.id === requested) ?? visibleTabs[0] ?? TAB_META[0];
  const allowed = active.anyOf.length === 0 || hasAnyPerm(active.anyOf);

  return (
    <div className="pt-8">
      <NavBar />
      <div className="mx-auto max-w-5xl px-4 pb-16">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-ink">Command Center</h1>
            <p className="text-sm text-ink-faint">
              Live operational view across the running platform.
            </p>
          </div>
          <StatusPulse status="ok" label="System Live" />
        </header>

        <div className="mb-6 flex flex-wrap gap-2 border-b border-hair pb-3">
          {(visibleTabs.length ? visibleTabs : [TAB_META[0]]).map((t) => (
            <button
              key={t.id}
              onClick={() => setParams({ tab: t.id }, { replace: true })}
              className={
                "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors " +
                (t.id === active.id
                  ? "bg-accent-command/15 text-accent-command"
                  : "text-ink-faint hover:bg-surface-2 hover:text-ink")
              }
            >
              {t.label}
            </button>
          ))}
        </div>

        {allowed ? RENDERERS[active.id]() : <PermissionNotice anyOf={active.anyOf} />}
      </div>
    </div>
  );
}
