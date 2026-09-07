import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { hasSession } from "../lib/auth";

/**
 * A *session* (refresh token within its window) is enough — the access token
 * may be stale offline; the sync path refreshes it before any write. Only when
 * there is no session at all do we bounce to /login.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  if (!hasSession()) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
