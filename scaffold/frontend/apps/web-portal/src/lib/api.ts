/**
 * Thin fetch wrappers for the two services this slice talks to.
 *
 * Paths are proxied same-origin by Vite (see vite.config.ts):
 *   /api/iam/*  -> iam-service   (:8001)
 *   /api/case/* -> case-service  (:8002)
 */
import { clearToken, getToken } from "./auth";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** A FastAPI 422 detail entry. */
export interface ValidationItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

async function requestRaw<T>(
  base: string,
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<{ status: number; data: T }> {
  const { auth = false, headers, ...rest } = init;
  const h = new Headers(headers);
  if (!h.has("Content-Type") && rest.body) h.set("Content-Type", "application/json");
  if (auth) {
    const token = getToken();
    if (token) h.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${base}${path}`, { ...rest, headers: h });

  if (res.status === 401 && auth) {
    // token rejected by the service — drop it so route guards send us to /login
    clearToken();
  }

  const text = await res.text();
  const data = text ? safeJson(text) : null;

  if (!res.ok) {
    let detail: string = res.statusText;
    if (data && typeof data === "object" && "detail" in data) {
      const d = (data as { detail: unknown }).detail;
      detail = typeof d === "string" ? d : `${res.status} ${res.statusText}`;
    }
    throw new ApiError(res.status, detail, data);
  }
  return { status: res.status, data: data as T };
}

function request<T>(
  base: string,
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  return requestRaw<T>(base, path, init).then((r) => r.data);
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/** Pull FastAPI 422 field errors out of an ApiError, keyed by the last `loc` segment. */
export function validationErrors(err: unknown): Record<string, string> {
  if (!(err instanceof ApiError) || err.status !== 422) return {};
  const body = err.body as { detail?: unknown } | undefined;
  const items = Array.isArray(body?.detail) ? (body!.detail as ValidationItem[]) : [];
  const out: Record<string, string> = {};
  for (const item of items) {
    const field = String(item.loc?.[item.loc.length - 1] ?? "_");
    if (!out[field]) out[field] = item.msg;
  }
  return out;
}

// --- iam-service ---------------------------------------------------------
export interface LoginResult {
  mfa_token: string;
  mfa_enrolled: boolean;
  token_type: "bearer";
  expires_in: number;
}
export interface MfaEnrollment {
  secret: string;
  otpauth_uri: string;
}
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export const iam = {
  login: (badge_number: string, password: string) =>
    request<LoginResult>("/api/iam", "/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ badge_number, password }),
    }),

  enrollMfa: (mfaToken: string) =>
    request<MfaEnrollment>("/api/iam", "/api/v1/auth/mfa/enroll", {
      method: "POST",
      headers: { Authorization: `Bearer ${mfaToken}` },
    }),

  verifyMfa: (mfa_token: string, code: string) =>
    request<TokenPair>("/api/iam", "/api/v1/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify({ mfa_token, code }),
    }),
};

// --- case-service ------------------------------------------------------
export interface Case {
  id: string;
  case_number: string;
  incident_id: string | null;
  status: "open" | "investigating" | "referred_prosecution" | "closed" | "suspended";
  lead_officer_id: string;
  opened_at: string;
  closed_at: string | null;
}

export interface IncidentCreate {
  reported_by: string;
  incident_type: string;
  description: string;
  station_id: string;
  reported_at: string; // ISO 8601
}

export interface Incident extends IncidentCreate {
  id: string;
  created_at: string;
  latitude: number | null;
  longitude: number | null;
}

export const incidents = {
  /**
   * POST /incidents. The caller owns the `idempotencyKey` lifetime — pass the
   * SAME key when retrying a failed submission so case-service dedupes it (the
   * key is stored as client_sync_id). A first write returns 201; a replay of the
   * same key returns 200 with the original record — surfaced here as `replayed`.
   */
  create: async (
    body: IncidentCreate,
    idempotencyKey: string,
  ): Promise<{ incident: Incident; replayed: boolean }> => {
    const { status, data } = await requestRaw<Incident>("/api/case", "/api/v1/incidents", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": idempotencyKey },
      auth: true,
    });
    return { incident: data, replayed: status === 200 };
  },
};

export const cases = {
  list: (params: { status?: string } = {}) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return request<Case[]>("/api/case", `/api/v1/cases${qs ? `?${qs}` : ""}`, { auth: true });
  },

  /** POST /cases — escalate an incident into a formal case (FR-CASE-02). */
  create: (body: { incident_id?: string | null; lead_officer_id: string }) =>
    request<Case>("/api/case", "/api/v1/cases", {
      method: "POST",
      body: JSON.stringify(body),
      auth: true,
    }),
};

// --- dashboard-service (CQRS read models) -----------------------------
export interface CrimeTrendBucket {
  month: string; // date (first of month)
  incident_type: string | null;
  count: number;
}

export interface KpiSnapshot {
  station_id: string | null;
  as_of: string;
  cases: {
    opened: number;
    closed: number;
    arrests_recorded: number;
    avg_case_age_days: number | null;
  };
  crime_trends: CrimeTrendBucket[];
  evidence_integrity: {
    evidence_logged: number;
    pending_transfer_ack: number;
    hash_mismatches: number;
  };
}

export const dashboard = {
  /** GET /dashboard/kpis — station-scoped when station_id given, else force-wide.
   *  `from`/`to` (YYYY-MM-DD) bound both the case day-buckets and the trend months. */
  kpis: (params: { station_id?: string; from?: string; to?: string } = {}) => {
    const clean = Object.fromEntries(
      Object.entries(params).filter(([, v]) => v),
    ) as Record<string, string>;
    const qs = new URLSearchParams(clean).toString();
    return request<KpiSnapshot>(
      "/api/dash",
      `/api/v1/dashboard/kpis${qs ? `?${qs}` : ""}`,
      { auth: true },
    );
  },
};
