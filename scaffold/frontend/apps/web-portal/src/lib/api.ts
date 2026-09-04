/**
 * Thin fetch wrappers for the services this slice talks to.
 *
 * Paths are proxied same-origin by Vite (see vite.config.ts):
 *   /api/iam/*      -> iam-service       (:8001)
 *   /api/case/*     -> case-service      (:8002)
 *   /api/dash/*     -> dashboard-service (:8007)
 *   /api/evidence/* -> evidence-service  (:8003)
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
  // Leave FormData alone — the browser sets the multipart boundary itself; only
  // JSON bodies need an explicit Content-Type.
  if (!h.has("Content-Type") && rest.body && !(rest.body instanceof FormData)) {
    h.set("Content-Type", "application/json");
  }
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

export interface ArrestCreate {
  officer_id: string;
  suspect_id: string;
  arrest_date: string; // ISO 8601
  location?: string | null;
  legal_basis?: string | null;
}

export interface Arrest extends ArrestCreate {
  id: string;
  case_id: string;
}

export type PartyType = "witness" | "suspect" | "victim";

export interface StatementCreate {
  recorded_by: string;
  party_type: PartyType;
  statement_text: string;
}

export interface Statement extends StatementCreate {
  id: string;
  case_id: string;
  recorded_at: string;
}

export interface CourtProceedingCreate {
  hearing_date: string; // ISO 8601
  court_name?: string | null;
  verdict?: string | null;
  notes?: string | null;
}

export interface CourtProceeding extends CourtProceedingCreate {
  id: string;
  case_id: string;
}

export const cases = {
  list: (params: { status?: string } = {}) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return request<Case[]>("/api/case", `/api/v1/cases${qs ? `?${qs}` : ""}`, { auth: true });
  },

  get: (id: string) => request<Case>("/api/case", `/api/v1/cases/${id}`, { auth: true }),

  /** POST /cases — escalate an incident into a formal case (FR-CASE-02). */
  create: (body: { incident_id?: string | null; lead_officer_id: string }) =>
    request<Case>("/api/case", "/api/v1/cases", {
      method: "POST",
      body: JSON.stringify(body),
      auth: true,
    }),

  /** GET /cases/{id}/arrests — arrests recorded against a case, newest first. */
  arrests: (caseId: string) =>
    request<Arrest[]>("/api/case", `/api/v1/cases/${caseId}/arrests`, { auth: true }),

  /** POST /cases/{id}/arrests — record an arrest (FR-CASE-04). Publishes
   * `ArrestRecorded`, which flows through the outbox into dashboard-service's
   * `cases.arrests_recorded` KPI. */
  recordArrest: (caseId: string, body: ArrestCreate) =>
    request<Arrest>("/api/case", `/api/v1/cases/${caseId}/arrests`, {
      method: "POST",
      body: JSON.stringify(body),
      auth: true,
    }),

  /** GET /cases/{id}/statements — witness/suspect/victim statements, newest first. */
  statements: (caseId: string) =>
    request<Statement[]>("/api/case", `/api/v1/cases/${caseId}/statements`, {
      auth: true,
    }),

  /** POST /cases/{id}/statements — record a statement (FR-CASE-05). Publishes
   * `StatementRecorded` to the audit trail. */
  recordStatement: (caseId: string, body: StatementCreate) =>
    request<Statement>("/api/case", `/api/v1/cases/${caseId}/statements`, {
      method: "POST",
      body: JSON.stringify(body),
      auth: true,
    }),

  /** GET /cases/{id}/court-proceedings — hearings recorded against a case,
   * newest first. */
  courtProceedings: (caseId: string) =>
    request<CourtProceeding[]>(
      "/api/case",
      `/api/v1/cases/${caseId}/court-proceedings`,
      { auth: true },
    ),

  /** POST /cases/{id}/court-proceedings — record a court proceeding
   * (FR-CASE-06). Publishes `CourtProceedingRecorded` to the audit trail. */
  recordCourtProceeding: (caseId: string, body: CourtProceedingCreate) =>
    request<CourtProceeding>(
      "/api/case",
      `/api/v1/cases/${caseId}/court-proceedings`,
      {
        method: "POST",
        body: JSON.stringify(body),
        auth: true,
      },
    ),
};

// --- evidence-service ----------------------------------------------------
export interface EvidenceItem {
  id: string;
  case_id: string;
  item_type: string;
  description: string;
  collected_by: string;
  collected_at: string;
  storage_ref: string | null;
  sha256_hash: string | null;
  status: "logged" | "in_analysis" | "in_court" | "disposed";
}

export type CustodyAction =
  | "collected"
  | "transferred"
  | "analyzed"
  | "stored"
  | "submitted_court"
  | "disposed";

export interface CustodyEvent {
  id: number;
  evidence_id: string;
  action: CustodyAction;
  from_officer: string | null;
  to_officer: string | null;
  acknowledgement: boolean;
  occurred_at: string;
}

export interface HashVerification {
  evidence_id: string;
  stored_hash: string;
  computed_hash: string;
  match: boolean;
  verified_at: string;
}

export const evidence = {
  /** POST /evidence (multipart/form-data) — FR-EVID-01/02. `file` is optional
   * (physical items have none); when present it's SHA-256 hashed server-side. */
  create: (form: FormData) =>
    request<EvidenceItem>("/api/evidence", "/api/v1/evidence", {
      method: "POST",
      body: form,
      auth: true,
    }),

  get: (id: string) =>
    request<EvidenceItem>("/api/evidence", `/api/v1/evidence/${id}`, { auth: true }),

  /** GET /evidence/{id}/custody — the append-only chain, chronological (FR-EVID-03/07). */
  custody: (id: string) =>
    request<CustodyEvent[]>("/api/evidence", `/api/v1/evidence/${id}/custody`, { auth: true }),

  /** POST /evidence/{id}/verify — recompute + compare the SHA-256 (FR-EVID-06). */
  verify: (id: string) =>
    request<HashVerification>("/api/evidence", `/api/v1/evidence/${id}/verify`, {
      method: "POST",
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
