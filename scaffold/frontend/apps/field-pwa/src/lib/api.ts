/**
 * Thin fetch wrappers for iam-service and case-service.
 *
 * Vite proxies same-origin paths in dev:
 *   /api/iam/*  -> iam-service  (:8001)
 *   /api/case/* -> case-service (:8002)
 *
 * A failed fetch (TypeError — offline, DNS, connection refused) is surfaced as
 * `ApiError` with `offline: true`, so callers can distinguish "can't reach the
 * server" from "server said no".
 */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public opts: { offline?: boolean; body?: unknown } = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
  get offline(): boolean {
    return this.opts.offline === true;
  }
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface IncidentInput {
  reported_by: string;
  incident_type: string;
  description: string;
  station_id: string;
  reported_at: string; // ISO 8601
}

export interface Incident extends IncidentInput {
  id: string;
  created_at: string;
  latitude: number | null;
  longitude: number | null;
}

export interface CaseRow {
  id: string;
  case_number: string;
  incident_id: string | null;
  status: string;
  lead_officer_id: string;
  opened_at: string;
  closed_at: string | null;
}

async function raw<T>(
  base: string,
  path: string,
  init: RequestInit & { token?: string } = {},
): Promise<{ status: number; data: T }> {
  const { token, headers, ...rest } = init;
  const h = new Headers(headers);
  if (rest.body && !h.has("Content-Type")) h.set("Content-Type", "application/json");
  if (token) h.set("Authorization", `Bearer ${token}`);

  let res: Response;
  try {
    res = await fetch(`${base}${path}`, { ...rest, headers: h });
  } catch {
    throw new ApiError(0, "network unavailable", { offline: true });
  }

  const text = await res.text();
  const data = text ? safeJson(text) : null;
  if (!res.ok) {
    let detail = res.statusText;
    if (data && typeof data === "object" && "detail" in data) {
      const d = (data as { detail: unknown }).detail;
      if (typeof d === "string") detail = d;
    }
    throw new ApiError(res.status, detail, { body: data });
  }
  return { status: res.status, data: data as T };
}

function safeJson(t: string): unknown {
  try {
    return JSON.parse(t);
  } catch {
    return t;
  }
}

export const iam = {
  login: (badge_number: string, password: string) =>
    raw<{ mfa_token: string; mfa_enrolled: boolean }>("/api/iam", "/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ badge_number, password }),
    }).then((r) => r.data),

  enrollMfa: (mfaToken: string) =>
    raw<{ secret: string; otpauth_uri: string }>("/api/iam", "/api/v1/auth/mfa/enroll", {
      method: "POST",
      headers: { Authorization: `Bearer ${mfaToken}` },
    }).then((r) => r.data),

  verifyMfa: (mfa_token: string, code: string) =>
    raw<TokenPair>("/api/iam", "/api/v1/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify({ mfa_token, code }),
    }).then((r) => r.data),

  refresh: (refresh_token: string) =>
    raw<TokenPair>("/api/iam", "/api/v1/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token }),
    }).then((r) => r.data),
};

export const cases = {
  list: (token: string) =>
    raw<CaseRow[]>("/api/case", "/api/v1/cases", { token }).then((r) => r.data),
};

export const incidents = {
  /**
   * POST /incidents with the caller-owned Idempotency-Key. 201 = created,
   * 200 = the server already had this key (a replay) — both return the record.
   */
  create: (body: IncidentInput, idempotencyKey: string, token: string) =>
    raw<Incident>("/api/case", "/api/v1/incidents", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": idempotencyKey },
      token,
    }).then((r) => ({ incident: r.data, replayed: r.status === 200 })),
};
