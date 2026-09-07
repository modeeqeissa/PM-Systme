/**
 * IndexedDB — the field PWA's local store. Two jobs:
 *   1. `cases`  — a read cache of the officer's cases, refreshed on every sync,
 *      rendered as-is when offline.
 *   2. `outbox` — incidents filed while offline (or whose POST failed). Each row
 *      keeps the SAME idempotency key for every replay, so case-service dedupes
 *      a retry into the original record.
 *   3. `meta`   — small key/value (last successful sync time).
 */
import { openDB, type DBSchema, type IDBPDatabase } from "idb";
import type { IncidentInput } from "./api";

export interface CachedCase {
  id: string;
  case_number: string;
  incident_id: string | null;
  status: string;
  lead_officer_id: string;
  opened_at: string;
  closed_at: string | null;
}

export type OutboxState = "queued" | "synced" | "rejected";

export interface OutboxIncident {
  /** local id (uuid) — the row key */
  id: string;
  /** the Idempotency-Key sent to case-service; stable across every retry */
  key: string;
  body: IncidentInput;
  state: OutboxState;
  attempts: number;
  createdAt: number;
  lastError?: string;
  /** server incident id once synced (201) or matched (200 replay) */
  remoteId?: string;
}

interface FieldDB extends DBSchema {
  cases: { key: string; value: CachedCase };
  outbox: { key: string; value: OutboxIncident; indexes: { by_state: OutboxState } };
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

// --- outbox ----------------------------------------------------------
export async function enqueueIncident(row: OutboxIncident): Promise<void> {
  const d = await db();
  await d.put("outbox", row);
}

export async function outboxAll(): Promise<OutboxIncident[]> {
  const d = await db();
  const all = await d.getAll("outbox");
  return all.sort((a, b) => a.createdAt - b.createdAt);
}

export async function outboxQueued(): Promise<OutboxIncident[]> {
  const d = await db();
  return (await d.getAllFromIndex("outbox", "by_state", "queued")).sort(
    (a, b) => a.createdAt - b.createdAt,
  );
}

export async function updateOutbox(
  id: string,
  patch: Partial<OutboxIncident>,
): Promise<void> {
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
  const d = await db();
  await d.put("meta", ts, "lastSyncAt");
}

export async function getLastSync(): Promise<number | null> {
  const d = await db();
  return ((await d.get("meta", "lastSyncAt")) as number | undefined) ?? null;
}
