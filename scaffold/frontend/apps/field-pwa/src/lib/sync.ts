/**
 * The offline-sync engine.
 *
 * Filing an incident ALWAYS writes to the IndexedDB outbox first, then tries to
 * flush — so a write is never lost to a crash or a dead network. A flush:
 *   1. ensures a usable access token, refreshing it via the rotating refresh
 *      token if it has expired (this is the "reconnect-to-refresh" story);
 *   2. POSTs each queued incident to case-service with its stable
 *      Idempotency-Key — a 201 or a 200 (server already had the key) both
 *      clear the row; a 4xx validation error marks it `rejected` (won't retry
 *      forever); a network failure leaves it `queued`;
 *   3. refreshes the local case cache.
 *
 * Runs on: app start, the `online` event, a 30s interval, and right after
 * fileIncident().
 */
import { newIdempotencyKey } from "@pmp/core";
import { ApiError, cases, iam, incidents, type IncidentInput } from "./api";
import {
  accessTokenUsable,
  getAccessToken,
  getRefreshToken,
  hasSession,
  updateTokens,
} from "./auth";
import {
  enqueueIncident,
  outboxQueued,
  pendingCount,
  putCases,
  setLastSync,
  updateOutbox,
  type OutboxIncident,
} from "./db";

export interface SyncResult {
  online: boolean;
  refreshed: boolean;
  synced: number;
  rejected: number;
  stillQueued: number;
  casesUpdated: boolean;
  needsReauth: boolean;
  error?: string;
}

/**
 * Persist an incident to the outbox and return its local row id. Does NOT
 * flush — the caller decides (the page awaits syncNow() for immediate
 * feedback; the online-event / interval sweeps catch it otherwise). Keeping
 * these separate means the write is durably saved before any network attempt.
 */
export async function fileIncident(body: IncidentInput): Promise<string> {
  const row: OutboxIncident = {
    id: newIdempotencyKey(),
    key: newIdempotencyKey(),
    body,
    state: "queued",
    attempts: 0,
    createdAt: Date.now(),
  };
  await enqueueIncident(row);
  return row.id;
}

async function ensureAccessToken(): Promise<{
  token: string | null;
  refreshed: boolean;
  needsReauth: boolean;
}> {
  if (accessTokenUsable()) {
    return { token: getAccessToken(), refreshed: false, needsReauth: false };
  }
  const refresh = getRefreshToken();
  if (!refresh) return { token: null, refreshed: false, needsReauth: true };
  try {
    const pair = await iam.refresh(refresh);
    updateTokens(pair.access_token, pair.refresh_token);
    return { token: pair.access_token, refreshed: true, needsReauth: false };
  } catch (e) {
    if (e instanceof ApiError && e.offline) {
      return { token: null, refreshed: false, needsReauth: false };
    }
    // server rejected the refresh token (expired or rotated away) -> re-login
    return { token: null, refreshed: false, needsReauth: true };
  }
}

let _running: Promise<SyncResult> | null = null;

export function syncNow(): Promise<SyncResult> {
  if (_running == null) {
    _running = _sync().finally(() => {
      _running = null;
    });
  }
  return _running;
}

async function _sync(): Promise<SyncResult> {
  const r: SyncResult = {
    online: true,
    refreshed: false,
    synced: 0,
    rejected: 0,
    stillQueued: 0,
    casesUpdated: false,
    needsReauth: false,
  };

  if (typeof navigator !== "undefined" && !navigator.onLine) {
    r.online = false;
    r.stillQueued = await pendingCount();
    return r;
  }

  const { token, refreshed, needsReauth } = await ensureAccessToken();
  r.refreshed = refreshed;
  if (needsReauth) {
    r.needsReauth = true;
    r.stillQueued = await pendingCount();
    return r;
  }
  if (token == null) {
    r.online = false; // refresh call itself failed to reach the server
    r.stillQueued = await pendingCount();
    return r;
  }

  for (const row of await outboxQueued()) {
    try {
      const { incident } = await incidents.create(row.body, row.key, token);
      await updateOutbox(row.id, {
        state: "synced",
        remoteId: incident.id,
        attempts: row.attempts + 1,
        lastError: undefined,
      });
      r.synced += 1;
    } catch (e) {
      if (e instanceof ApiError && e.offline) {
        await updateOutbox(row.id, { attempts: row.attempts + 1, lastError: "offline" });
        r.online = false;
        break;
      }
      const validationError =
        e instanceof ApiError &&
        e.status >= 400 &&
        e.status < 500 &&
        e.status !== 401 &&
        e.status !== 429;
      if (validationError) {
        await updateOutbox(row.id, {
          state: "rejected",
          attempts: row.attempts + 1,
          lastError: `${(e as ApiError).status} ${(e as Error).message}`,
        });
        r.rejected += 1;
      } else {
        await updateOutbox(row.id, {
          attempts: row.attempts + 1,
          lastError: e instanceof Error ? e.message : String(e),
        });
      }
    }
  }

  if (r.online) {
    try {
      await putCases(await cases.list(token));
      await setLastSync(Date.now());
      r.casesUpdated = true;
    } catch (e) {
      if (e instanceof ApiError && e.offline) r.online = false;
      else r.error = e instanceof Error ? e.message : String(e);
    }
  }

  r.stillQueued = await pendingCount();
  return r;
}

let _wired = false;

/** Wire the `online` event + a periodic sweep. Idempotent. */
export function startBackgroundSync(): void {
  if (_wired || typeof window === "undefined") return;
  _wired = true;
  window.addEventListener("online", () => {
    if (hasSession()) void syncNow().catch(() => {});
  });
  window.setInterval(() => {
    if (hasSession() && navigator.onLine) void syncNow().catch(() => {});
  }, 30_000);
}
