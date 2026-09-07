import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Alert, Card } from "@pmp/ui";
import { hasAnyPerm } from "../lib/rbac";

/**
 * Route guard for a screen that is entirely gated on one or more permissions
 * (e.g. the HR directory, the discipline records). Sits *inside* RequireAuth —
 * the token is already known valid here. A caller who lacks every listed
 * permission gets a plain "not authorised" card instead of the screen making a
 * doomed request and rendering a raw 403; the nav also hides the link, so this
 * is the deep-link / typed-URL path.
 */
export function RequirePermission({
  anyOf,
  children,
}: {
  anyOf: string[];
  children: ReactNode;
}) {
  if (hasAnyPerm(anyOf)) return <>{children}</>;
  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <Card>
        <Alert variant="error">
          Your role doesn't have access to this area (needs one of:{" "}
          {anyOf.map((c, i) => (
            <span key={c}>
              {i > 0 && ", "}
              <code>{c}</code>
            </span>
          ))}
          ).
        </Alert>
        <Link to="/cases" className="mt-4 inline-block text-sm text-ink-faint underline">
          ← Back to cases
        </Link>
      </Card>
    </div>
  );
}

/**
 * Inline (non-route) version — for a Command Center tab-panel whose own
 * permission the caller lacks. Same "API is the real authority, this only
 * decides what to show" contract as RequirePermission.
 */
export function PermissionNotice({ anyOf }: { anyOf: string[] }) {
  return (
    <Alert variant="error">
      This panel needs one of:{" "}
      {anyOf.map((c, i) => (
        <span key={c}>
          {i > 0 && ", "}
          <code>{c}</code>
        </span>
      ))}
      . Your role holds none of them.
    </Alert>
  );
}
