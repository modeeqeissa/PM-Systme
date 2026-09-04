import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { hasValidToken } from "../lib/auth";

/**
 * Route guard: renders children only when a non-expired access token is present,
 * otherwise redirects to /login (remembering where we were headed).
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation();
  if (!hasValidToken()) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}
