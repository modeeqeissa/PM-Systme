import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it } from "vitest";
import {
  _resetDbForTests,
  enqueueIncident,
  getCases,
  getLastSync,
  outboxAll,
  outboxQueued,
  pendingCount,
  putCases,
  setLastSync,
  updateOutbox,
  type OutboxIncident,
} from "../lib/db";

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory();
  _resetDbForTests();
});

const incident = (over: Partial<OutboxIncident> = {}): OutboxIncident => ({
  id: crypto.randomUUID(),
  key: crypto.randomUUID(),
  body: {
    reported_by: "u-1",
    incident_type: "theft",
    description: "bike gone",
    station_id: "s-1",
    reported_at: "2026-09-07T08:00:00.000Z",
  },
  state: "queued",
  attempts: 0,
  createdAt: Date.now(),
  ...over,
});

describe("field IndexedDB", () => {
  it("round-trips the cached case list, newest first", async () => {
    await putCases([
      { id: "c1", case_number: "CASE-1", incident_id: null, status: "open", lead_officer_id: "u", opened_at: "2026-01-01T00:00:00Z", closed_at: null },
      { id: "c2", case_number: "CASE-2", incident_id: null, status: "open", lead_officer_id: "u", opened_at: "2026-03-01T00:00:00Z", closed_at: null },
    ]);
    const rows = await getCases();
    expect(rows.map((r) => r.id)).toEqual(["c2", "c1"]);

    // putCases replaces the whole cache
    await putCases([{ id: "c3", case_number: "CASE-3", incident_id: null, status: "open", lead_officer_id: "u", opened_at: "2026-02-01T00:00:00Z", closed_at: null }]);
    expect((await getCases()).map((r) => r.id)).toEqual(["c3"]);
  });

  it("queues incidents and lets them transition out of 'queued'", async () => {
    const a = incident();
    const b = incident({ createdAt: Date.now() + 50 });
    await enqueueIncident(a);
    await enqueueIncident(b);
    expect(await pendingCount()).toBe(2);
    expect((await outboxQueued()).map((r) => r.id)).toEqual([a.id, b.id]);

    await updateOutbox(a.id, { state: "synced", remoteId: "srv-1", attempts: 1 });
    expect(await pendingCount()).toBe(1);
    expect((await outboxAll()).find((r) => r.id === a.id)?.remoteId).toBe("srv-1");
  });

  it("stores the last-sync timestamp", async () => {
    expect(await getLastSync()).toBeNull();
    await setLastSync(1_700_000_000_000);
    expect(await getLastSync()).toBe(1_700_000_000_000);
  });
});
