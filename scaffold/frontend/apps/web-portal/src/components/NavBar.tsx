import { NavLink, useNavigate } from "react-router-dom";
import { Button } from "@pmp/ui";
import { clearToken, currentClaims } from "../lib/auth";
import { hasAnyPerm } from "../lib/rbac";

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
];

export function NavBar() {
  const navigate = useNavigate();
  const claims = currentClaims();
  const visible = ITEMS.filter((i) => hasAnyPerm(i.anyOf));

  return (
    <nav className="mb-6 border-b border-slate-200 pb-3">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-5 gap-y-2 px-4 text-sm">
        {visible.map((i) => (
          <NavLink
            key={i.to}
            to={i.to}
            className={({ isActive }) =>
              isActive
                ? "font-medium text-slate-900 underline decoration-slate-900"
                : "text-slate-500 hover:text-slate-900"
            }
          >
            {i.label}
          </NavLink>
        ))}
        <span className="ml-auto flex items-center gap-3 text-slate-500">
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
