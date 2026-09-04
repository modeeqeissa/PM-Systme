/**
 * Access-token storage + client-side validity check.
 *
 * The token is an RS256 JWT issued by iam-service. We do NOT verify the
 * signature in the browser (the API does that on every call); we only read the
 * `exp` claim so protected routes can bounce to /login before making a doomed
 * request.
 */
const STORAGE_KEY = "pmp.access_token";

export interface TokenClaims {
  sub: string;
  badge_number: string;
  station_id: string;
  roles: string[];
  permissions: string[];
  exp: number;
  iat: number;
}

function base64UrlDecode(segment: string): string {
  const padded = segment.replace(/-/g, "+").replace(/_/g, "/");
  return atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
}

export function decodeToken(token: string): TokenClaims | null {
  try {
    const [, payload] = token.split(".");
    if (!payload) return null;
    return JSON.parse(base64UrlDecode(payload)) as TokenClaims;
  } catch {
    return null;
  }
}

export function isExpired(claims: TokenClaims | null, skewSeconds = 10): boolean {
  if (!claims) return true;
  return claims.exp * 1000 <= Date.now() + skewSeconds * 1000;
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, token);
  } catch {
    /* private mode etc. — the app still works for this session via state */
  }
}

export function clearToken(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/** A usable token is present and not past its `exp`. */
export function hasValidToken(): boolean {
  const token = getToken();
  return token != null && !isExpired(decodeToken(token));
}

export function currentClaims(): TokenClaims | null {
  const token = getToken();
  return token ? decodeToken(token) : null;
}
