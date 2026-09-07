import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it } from "vitest";
import {
  _resetDbForTests,
  enqueue,
  getCase,
  getCases,
  getLastSync,
  outboxAll,
  outboxQueued,
  pendingCount,
  putCases,
  setLastSync,
  updateOutbox,
  type OutboxItem,
} from "../lib/db";

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory();
  _resetDbForTests();
});

const item = (over: Partial<OutboxItem> = {}): OutboxItem => ({
  id: crypto.randomUUID(),
  key: crypto.randomUUID(),
  kind: "incident",
  body: { incident_type: "theft", description: "bike gone", station_id: "s-1", reported_by: "u-1", reported_at: "2026-09-07T08:00:00.000Z" },
  state: "queued",
  attempts: 0,
  createdAt: Date.now(),
  ...over,
});

describe("field IndexedDB", () => {
  it("round-trips the cached case list, newest first, and getCase by id", async () => {
    await putCases([
      { id: "c1", case_number: "CASE-1", incident_id: null, status: "open", lead_officer_id: "u", opened_at: "2026-01-01T00:00:00Z", closed_at: null },
      { id: "c2", case_number: "CASE-2", incident_id: null, status: "open", lead_officer_id: "u", opened_at: "2026-03-01T00:00:00Z", closed_at: null },
    ]);
    expect((await getCases()).map((r) => r.id)).toEqual(["c2", "c1"]);
    expect((await getCase("c1"))?.case_number).toBe("CASE-1");

    await putCases([{ id: "c3", case_number: "CASE-3", incident_id: null, status: "open", lead_officer_id: "u", opened_at: "2026-02-01T00:00:00Z", closed_at: null }]);
    expect((await getCases()).map((r) => r.id)).toEqual(["c3"]);
  });

  it("queues mixed-kind writes and transitions them out of 'queued'", async () => {
    const inc = item();
    const stmt = item({ kind: "statement", caseId: "case-9", createdAt: Date.now() + 50 });
    await enqueue(inc);
    await enqueue(stmt);
    expect(await pendingCount()).toBe(2);
    expect((await outboxQueued()).map((r) => r.kind)).toEqual(["incident", "statement"]);

    await updateOutbox(inc.id, { state: "synced", remoteId: "srv-1", attempts: 1 });
    expect(await pendingCount()).toBe(1);
    expect((await outboxAll()).find((r) => r.id === inc.id)?.remoteId).toBe("srv-1");
  });

  it("stores evidence file bytes (base64) and gives them back intact", async () => {
    const ev = item({
      kind: "evidence",
      caseId: "case-1",
      fileB64: btoa("hello-evidence-bytes"),
      fileType: "image/png",
      fileName: "photo.png",
    });
    await enqueue(ev);
    const back = (await outboxAll()).find((r) => r.id === ev.id)!;
    expect(typeof back.fileB64).toBe("string");
    expect(atob(back.fileB64!)).toBe("hello-evidence-bytes");
    expect(back.fileName).toBe("photo.png");
  });

  it("stores the last-sync timestamp", async () => {
    expect(await getLastSync()).toBeNull();
    await setLastSync(1_700_000_000_000);
    expect(await getLastSync()).toBe(1_700_000_000_000);
  });
});
