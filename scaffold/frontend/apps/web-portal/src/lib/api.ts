/**
 * Thin fetch wrappers for the two services this slice talks to.
 *
 * Paths are proxied same-origin by Vite (see vite.config.ts):
 *   /iam/*  -> iam-service   (:8001)
 *   /case/* -> case-service  (:8002)
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

async function request<T>(
  base: string,
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<T> {
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
      detail = String((data as { detail: unknown }).detail);
    }
    throw new ApiError(res.status, detail, data);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
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

export const cases = {
  list: (params: { status?: string } = {}) => {
    const qs = new URLSearchParams(params as Record<string, string>).toString();
    return request<Case[]>("/api/case", `/api/v1/cases${qs ? `?${qs}` : ""}`, { auth: true });
  },
};
