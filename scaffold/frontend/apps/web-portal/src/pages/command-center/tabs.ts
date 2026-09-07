/** Command Center tab metadata — kept separate from CommandCenterPage so the
 *  NavBar can import COMMAND_CENTER_PERMS without a circular dependency
 *  (CommandCenterPage renders <NavBar/>). */
export interface TabMeta {
  id: string;
  label: string;
  /** permission codes gating this panel; empty = auth only */
  anyOf: string[];
}

export const TAB_META: TabMeta[] = [
  { id: "health", label: "System Health", anyOf: [] },
  { id: "kpis", label: "Live KPIs", anyOf: ["dashboard.view"] },
  { id: "audit", label: "Audit & Activity", anyOf: ["audit.read"] },
  { id: "users", label: "Users & Roles", anyOf: ["iam.user.read"] },
  { id: "integration", label: "Integration Gateway", anyOf: ["integration.read"] },
];

/** Every permission any tab cares about. The NavBar entry shows "Command
 *  Center" when the caller holds one of these — or always, while the list is
 *  empty (System Health needs no permission). Each panel still re-checks. */
export const COMMAND_CENTER_PERMS: string[] = Array.from(
  new Set(TAB_META.flatMap((t) => t.anyOf)),
);
