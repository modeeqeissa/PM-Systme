/**
 * Token storage for the field PWA.
 *
 * iam-service issues a short-lived access token (a JWT, 15 min) and a rotating
 * refresh token (an OPAQUE random string, 7 days server-side). Both are cached
 * in localStorage so a session survives an app restart with no network.
 *
 * Offline honesty (flagged shortcuts):
 *   - The access token WILL expire mid-shift with no connectivity. We cannot
 *     refresh it offline. Reads (the cached case list) still work; a new
 *     incident is always written to the local outbox FIRST so it is never
 *     lost, then the sync path refreshes the access token (once online) before
 *     replaying the queued write.
 *   - The refresh token is opaque, so its real expiry is only known to the
 *     server. Client-side we bound the offline session with a conservative
 *     7-day window from when the pair was obtained (matches iam's default
 *     REFRESH_TOKEN_TTL; if iam is reconfigured shorter this heuristic is
 *     optimistic — the server still rejects a truly-expired token on refresh,
 *     and the sync surfaces that instead of dropping queued work).
 */
const ACCESS_KEY = "pmp.field.access_token";
const REFRESH_KEY = "pmp.field.refresh_token";
const OBTAINED_KEY = "pmp.field.tokens_obtained_at";

const REFRESH_WINDOW_MS = 7 * 24 * 3600 * 1000;

export interface AccessClaims {
  sub: string;
  badge_number: string;
  station_id: string;
  roles: string[];
  permissions: string[];
  exp: number;
  iat: number;
}

function b64urlDecode(seg: string): string {
  const s = seg.replace(/-/g, "+").replace(/_/g, "/");
  return atob(s + "=".repeat((4 - (s.length % 4)) % 4));
}

export function decodeJwt<T>(token: string | null): T | null {
  if (!token) return null;
  try {
    const [, payload] = token.split(".");
    return payload ? (JSON.parse(b64urlDecode(payload)) as T) : null;
  } catch {
    return null;
  }
}

export function isExpired(claims: { exp: number } | null, skewSeconds = 15): boolean {
  if (!claims) return true;
  return claims.exp * 1000 <= Date.now() + skewSeconds * 1000;
}

function get(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function getAccessToken(): string | null {
  return get(ACCESS_KEY);
}
export function getRefreshToken(): string | null {
  return get(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string): void {
  try {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
    localStorage.setItem(OBTAINED_KEY, String(Date.now()));
  } catch {
    /* private mode — runs for this session without persistence */
  }
}

/** Replace just the access token after a successful refresh (refresh token rotates too). */
export function updateTokens(access: string, refresh: string): void {
  setTokens(access, refresh);
}

export function clearTokens(): void {
  try {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(OBTAINED_KEY);
  } catch {
    /* ignore */
  }
}

export function accessClaims(): AccessClaims | null {
  return decodeJwt<AccessClaims>(getAccessToken());
}

/** Access token present and still valid — safe to call the API right now. */
export function accessTokenUsable(): boolean {
  return getAccessToken() != null && !isExpired(accessClaims());
}

/**
 * A usable *session* exists: a refresh token is stored and the conservative
 * offline window has not elapsed. The access token may be stale — the sync
 * path refreshes it before any write.
 */
export function hasSession(): boolean {
  if (getRefreshToken() == null) return false;
  const obtained = Number(get(OBTAINED_KEY) ?? "0");
  return obtained > 0 && Date.now() - obtained < REFRESH_WINDOW_MS;
}
