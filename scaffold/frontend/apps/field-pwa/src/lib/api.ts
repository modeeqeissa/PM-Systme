/**
 * Thin fetch wrappers for iam-service, case-service and evidence-service.
 *
 * Vite proxies same-origin paths in dev:
 *   /api/iam/*      -> iam-service      (:8001)
 *   /api/case/*     -> case-service     (:8002)
 *   /api/evidence/* -> evidence-service (:8003)
 *
 * A failed fetch (TypeError — offline, DNS, connection refused) is surfaced as
 * `ApiError` with `offline: true`, distinct from "server said no".
 */
import { base64ToArrayBuffer } from "./b64";
import type { OutboxItem } from "./db";

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
  // Don't set Content-Type for FormData — the browser adds the multipart boundary.
  if (rest.body && typeof rest.body === "string" && !h.has("Content-Type")) {
    h.set("Content-Type", "application/json");
  }
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

/**
 * Send one queued outbox item to its endpoint with its stable Idempotency-Key.
 * 201 (created) and 200 (server already had the key — a replay) both count as
 * success and return the server-assigned id.
 */
export async function submitOutboxItem(
  item: OutboxItem,
  token: string,
): Promise<{ remoteId: string }> {
  const key = item.key;

  if (item.kind === "incident") {
    const r = await raw<{ id: string }>("/api/case", "/api/v1/incidents", {
      method: "POST",
      body: JSON.stringify(item.body),
      headers: { "Idempotency-Key": key },
      token,
    });
    return { remoteId: r.data.id };
  }

  if (item.kind === "statement" || item.kind === "arrest") {
    const seg = item.kind === "statement" ? "statements" : "arrests";
    const r = await raw<{ id: string }>(
      "/api/case",
      `/api/v1/cases/${item.caseId}/${seg}`,
      { method: "POST", body: JSON.stringify(item.body), headers: { "Idempotency-Key": key }, token },
    );
    return { remoteId: r.data.id };
  }

  // evidence — multipart; the file is rebuilt from the stored base64 string
  const fd = new FormData();
  for (const [k, v] of Object.entries(item.body)) fd.append(k, String(v));
  if (item.fileB64) {
    const blob = new Blob([base64ToArrayBuffer(item.fileB64)], {
      type: item.fileType || "application/octet-stream",
    });
    fd.append("file", blob, item.fileName ?? "evidence.bin");
  }
  const r = await raw<{ id: string }>("/api/evidence", "/api/v1/evidence", {
    method: "POST",
    body: fd,
    headers: { "Idempotency-Key": key },
    token,
  });
  return { remoteId: r.data.id };
}
