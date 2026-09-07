/**
 * IndexedDB — the field PWA's local store.
 *   1. `cases`  — a read cache of the officer's cases (refreshed each sync).
 *   2. `outbox` — field writes queued offline (or whose POST failed). Every
 *      row keeps ONE idempotency key across every replay so the server dedupes
 *      a retry into the original record. An `evidence` row also carries the
 *      file itself as a Blob until it syncs.
 *   3. `meta`   — last successful sync time.
 */
import { openDB, type DBSchema, type IDBPDatabase } from "idb";

export interface CachedCase {
  id: string;
  case_number: string;
  incident_id: string | null;
  status: string;
  lead_officer_id: string;
  opened_at: string;
  closed_at: string | null;
}

export type OutboxKind = "incident" | "statement" | "arrest" | "evidence";
export type OutboxState = "queued" | "synced" | "rejected";

export interface OutboxItem {
  /** local id (uuid) — the row key */
  id: string;
  kind: OutboxKind;
  /** the Idempotency-Key sent to the server; stable across every retry */
  key: string;
  /** case_id for statement / arrest / evidence; unused for incident */
  caseId?: string;
  /** JSON body (incident/statement/arrest) or the non-file evidence fields */
  body: Record<string, unknown>;
  /**
   * evidence only — the file's bytes, held here until sync, base64-encoded
   * (see lib/b64.ts for why a string and not a Blob/ArrayBuffer). The Blob is
   * reconstructed at submit time.
   */
  fileB64?: string;
  fileType?: string;
  fileName?: string;
  state: OutboxState;
  attempts: number;
  createdAt: number;
  lastError?: string;
  /** server-assigned id once synced (201) or matched (200 replay) */
  remoteId?: string;
}

interface FieldDB extends DBSchema {
  cases: { key: string; value: CachedCase };
  outbox: { key: string; value: OutboxItem; indexes: { by_state: OutboxState } };
  meta: { key: string; value: unknown };
}

const DB_NAME = "pmp-field";
const DB_VERSION = 1;

let _db: Promise<IDBPDatabase<FieldDB>> | null = null;

export function db(): Promise<IDBPDatabase<FieldDB>> {
  if (_db == null) {
    _db = openDB<FieldDB>(DB_NAME, DB_VERSION, {
      upgrade(d) {
        d.createObjectStore("cases", { keyPath: "id" });
        const ob = d.createObjectStore("outbox", { keyPath: "id" });
        ob.createIndex("by_state", "state");
        d.createObjectStore("meta");
      },
    });
  }
  return _db;
}

/** Test-only: forget the cached connection so a fresh (fake) IndexedDB is used. */
export function _resetDbForTests(): void {
  _db = null;
}

// --- cases cache -------------------------------------------------------
export async function putCases(cases: CachedCase[]): Promise<void> {
  const d = await db();
  const tx = d.transaction("cases", "readwrite");
  await tx.store.clear();
  for (const c of cases) await tx.store.put(c);
  await tx.done;
}

export async function getCases(): Promise<CachedCase[]> {
  const d = await db();
  const all = await d.getAll("cases");
  return all.sort((a, b) => (a.opened_at < b.opened_at ? 1 : -1));
}

export async function getCase(id: string): Promise<CachedCase | undefined> {
  return (await db()).get("cases", id);
}

// --- outbox ----------------------------------------------------------
export class OutboxQuotaError extends Error {
  constructor() {
    super("device storage is full — the item was NOT queued");
    this.name = "OutboxQuotaError";
  }
}

export async function enqueue(item: OutboxItem): Promise<void> {
  const d = await db();
  try {
    await d.put("outbox", item);
  } catch (e) {
    if (e instanceof DOMException && (e.name === "QuotaExceededError" || e.code === 22)) {
      throw new OutboxQuotaError();
    }
    throw e;
  }
}

export async function outboxAll(): Promise<OutboxItem[]> {
  const d = await db();
  return (await d.getAll("outbox")).sort((a, b) => a.createdAt - b.createdAt);
}

export async function outboxQueued(): Promise<OutboxItem[]> {
  const d = await db();
  return (await d.getAllFromIndex("outbox", "by_state", "queued")).sort(
    (a, b) => a.createdAt - b.createdAt,
  );
}

export async function updateOutbox(id: string, patch: Partial<OutboxItem>): Promise<void> {
  const d = await db();
  const cur = await d.get("outbox", id);
  if (cur == null) return;
  await d.put("outbox", { ...cur, ...patch });
}

export async function pendingCount(): Promise<number> {
  return (await outboxQueued()).length;
}

// --- meta ----------------------------------------------------------
export async function setLastSync(ts: number): Promise<void> {
  await (await db()).put("meta", ts, "lastSyncAt");
}

export async function getLastSync(): Promise<number | null> {
  return ((await (await db()).get("meta", "lastSyncAt")) as number | undefined) ?? null;
}

/** Best-effort storage headroom for a UI warning. null = API unavailable. */
export async function storageHeadroom(): Promise<{ usedMB: number; quotaMB: number; pctUsed: number } | null> {
  try {
    const est = await navigator.storage?.estimate?.();
    if (!est || est.quota == null || est.usage == null) return null;
    return {
      usedMB: est.usage / 1e6,
      quotaMB: est.quota / 1e6,
      pctUsed: (est.usage / est.quota) * 100,
    };
  } catch {
    return null;
  }
}
