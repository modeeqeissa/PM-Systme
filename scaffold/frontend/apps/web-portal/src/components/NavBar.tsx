import { NavLink, useNavigate } from "react-router-dom";
import { Button } from "@pmp/ui";
import { clearToken, currentClaims } from "../lib/auth";
import { hasAnyPerm } from "../lib/rbac";
import { COMMAND_CENTER_PERMS } from "../pages/command-center/tabs";

/**
 * Shared top navigation. Every entry is gated on the permission that its
 * destination screen requires, so a role never sees a link that would only
 * 403 (matches how the dashboard already hides itself). The API stays the
 * real authority.
 */
const ITEMS: { to: string; label: string; anyOf: string[] }[] = [
  { to: "/cases", label: "Cases", anyOf: ["case.read"] },
  { to: "/dashboard", label: "Dashboard", anyOf: ["dashboard.view"] },
  { to: "/hr/officers", label: "Officers", anyOf: ["hr.officer.read"] },
  { to: "/hr/transfers", label: "Transfer approvals", anyOf: ["hr.transfer.approve"] },
  { to: "/hr/leave", label: "Leave approvals", anyOf: ["hr.leave.approve"] },
  { to: "/training/courses", label: "Training", anyOf: ["training.cert.read"] },
  { to: "/training/issue", label: "Issue cert", anyOf: ["training.cert.write"] },
  { to: "/training/compliance", label: "Compliance", anyOf: ["training.cert.read"] },
  { to: "/community/meetings", label: "Community", anyOf: ["community.read"] },
  { to: "/community/concerns", label: "Concerns", anyOf: ["community.read"] },
  { to: "/community/follow-ups", label: "Follow-ups", anyOf: ["community.read"] },
  // Command Center: shown when the caller holds any permission a panel needs
  // (see COMMAND_CENTER_PERMS). Until a gated panel exists that list is empty,
  // and the entry is visible to any authenticated user (System Health needs
  // no permission). Each panel still re-checks its own code.
  { to: "/command-center", label: "Command Center", anyOf: COMMAND_CENTER_PERMS },
];

export function NavBar() {
  const navigate = useNavigate();
  const claims = currentClaims();
  const visible = ITEMS.filter((i) => i.anyOf.length === 0 || hasAnyPerm(i.anyOf));

  return (
    <nav className="mb-6 border-b border-hair bg-surface/60 py-3 backdrop-blur-panel">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-5 gap-y-2 px-4 text-sm">
        {visible.map((i) => (
          <NavLink
            key={i.to}
            to={i.to}
            className={({ isActive }) =>
              isActive
                ? "font-medium text-ink underline decoration-accent-command"
                : "text-ink-faint hover:text-ink"
            }
          >
            {i.label}
          </NavLink>
        ))}
        <span className="ml-auto flex items-center gap-3 text-ink-faint">
          {claims && <span className="font-medium">{claims.badge_number}</span>}
          <Button
            variant="secondary"
            onClick={() => {
              clearToken();
              navigate("/login", { replace: true });
            }}
          >
            Sign out
          </Button>
        </span>
      </div>
    </nav>
  );
}
