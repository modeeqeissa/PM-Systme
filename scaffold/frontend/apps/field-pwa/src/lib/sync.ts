/**
 * The offline-sync engine.
 *
 * Every field write (incident, statement, arrest, evidence) is persisted to the
 * IndexedDB outbox FIRST — never lost to a crash or a dead network — then a
 * flush is attempted:
 *   1. ensure a usable access token, refreshing it via the rotating refresh
 *      token if expired (reconnect-to-refresh);
 *   2. POST each queued item to its endpoint with its stable Idempotency-Key —
 *      201 or 200 (server already had the key) both clear the row; a 4xx
 *      validation error marks it `rejected`; a network failure leaves it
 *      `queued`;
 *   3. refresh the local case cache.
 *
 * Runs on app start, the `online` event, a 30s interval, and a page's explicit
 * syncNow().
 */
import { newIdempotencyKey } from "@pmp/core";
import { bytesToBase64 } from "./b64";
import { ApiError, cases, iam, submitOutboxItem } from "./api";
import {
  accessTokenUsable,
  getAccessToken,
  getRefreshToken,
  hasSession,
  updateTokens,
} from "./auth";
import {
  enqueue,
  outboxAll,
  outboxQueued,
  OutboxQuotaError,
  pendingCount,
  putCases,
  setLastSync,
  updateOutbox,
  type OutboxItem,
  type OutboxKind,
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

interface FileArgs {
  kind: OutboxKind;
  body: Record<string, unknown>;
  caseId?: string;
  file?: File;
}

/** Blob.arrayBuffer() with a FileReader fallback (jsdom / older WebView). */
function readArrayBuffer(f: Blob): Promise<ArrayBuffer> {
  if (typeof f.arrayBuffer === "function") return f.arrayBuffer();
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as ArrayBuffer);
    r.onerror = () => reject(r.error);
    r.readAsArrayBuffer(f);
  });
}

/** Persist a field write to the outbox. Returns the local row id. Does NOT flush. */
export async function queueWrite(args: FileArgs): Promise<string> {
  const row: OutboxItem = {
    id: newIdempotencyKey(),
    key: newIdempotencyKey(),
    kind: args.kind,
    caseId: args.caseId,
    body: args.body,
    state: "queued",
    attempts: 0,
    createdAt: Date.now(),
  };
  if (args.file) {
    // read the whole file into memory once and base64-encode it for storage
    // (see lib/b64.ts). Fine for field photos/PDFs; a video would need a
    // streamed approach — flagged for a later slice.
    row.fileB64 = bytesToBase64(await readArrayBuffer(args.file));
    row.fileType = args.file.type;
    row.fileName = args.file.name;
  }
  await enqueue(row); // throws OutboxQuotaError if the device is full
  return row.id;
}

export const fileIncident = (body: Record<string, unknown>) => queueWrite({ kind: "incident", body });
export const fileStatement = (caseId: string, body: Record<string, unknown>) =>
  queueWrite({ kind: "statement", caseId, body });
export const fileArrest = (caseId: string, body: Record<string, unknown>) =>
  queueWrite({ kind: "arrest", caseId, body });
export const fileEvidence = (caseId: string, body: Record<string, unknown>, file: File | undefined) =>
  queueWrite({ kind: "evidence", caseId, body, file });

export type WriteOutcome =
  | { kind: "synced" }
  | { kind: "queued" }
  | { kind: "rejected"; detail?: string }
  | { kind: "reauth" }
  | { kind: "quota" };

/**
 * Queue one field write, then attempt an immediate flush and report what
 * happened to that specific row — the shared path behind every "file X" form.
 */
export async function runQueuedWrite(enqueueFn: () => Promise<string>): Promise<WriteOutcome> {
  let localId: string;
  try {
    localId = await enqueueFn();
  } catch (e) {
    if (e instanceof OutboxQuotaError) return { kind: "quota" };
    throw e;
  }
  const r = await syncNow();
  if (r.needsReauth) return { kind: "reauth" };
  const row = (await outboxAll()).find((o) => o.id === localId);
  if (row?.state === "synced") return { kind: "synced" };
  if (row?.state === "rejected") return { kind: "rejected", detail: row.lastError };
  return { kind: "queued" };
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
    r.online = false;
    r.stillQueued = await pendingCount();
    return r;
  }

  for (const row of await outboxQueued()) {
    try {
      const { remoteId } = await submitOutboxItem(row, token);
      await updateOutbox(row.id, {
        state: "synced",
        remoteId,
        attempts: row.attempts + 1,
        lastError: undefined,
        // drop the file bytes once they're on the server — reclaim the space
        fileB64: undefined,
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
