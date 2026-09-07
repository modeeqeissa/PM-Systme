import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it, vi } from "vitest";

const submit = vi.fn();
const list = vi.fn();
const refresh = vi.fn();

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    iam: { ...actual.iam, refresh: (...a: unknown[]) => refresh(...a) },
    cases: { list: (...a: unknown[]) => list(...a) },
    submitOutboxItem: (...a: unknown[]) => submit(...a),
  };
});

import { ApiError } from "../lib/api";
import { _resetDbForTests, outboxAll, pendingCount, getCases, type OutboxItem } from "../lib/db";
import { fileArrest, fileEvidence, fileIncident, fileStatement, syncNow } from "../lib/sync";

function jwt(expDeltaSec: number): string {
  const enc = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const now = Math.floor(Date.now() / 1000);
  return [
    enc({ alg: "RS256" }),
    enc({ sub: "u-1", station_id: "s-1", roles: [], permissions: [], iat: now, exp: now + expDeltaSec }),
    "sig",
  ].join(".");
}
function setOnline(v: boolean) {
  Object.defineProperty(navigator, "onLine", { value: v, configurable: true });
}
function withTokens(accessExpSec: number) {
  localStorage.setItem("pmp.field.access_token", jwt(accessExpSec));
  localStorage.setItem("pmp.field.refresh_token", "opaque-refresh");
  localStorage.setItem("pmp.field.tokens_obtained_at", String(Date.now()));
}

const INCIDENT_BODY = {
  reported_by: "u-1",
  incident_type: "theft",
  description: "bike gone",
  station_id: "s-1",
  reported_at: "2026-09-07T08:00:00.000Z",
};

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory();
  _resetDbForTests();
  localStorage.clear();
  submit.mockReset();
  list.mockReset();
  refresh.mockReset();
  list.mockResolvedValue([]);
  setOnline(true);
});

describe("offline-sync engine", () => {
  it("queues a write when offline and submits nothing", async () => {
    setOnline(false);
    withTokens(900);
    await fileIncident(INCIDENT_BODY);
    expect(submit).not.toHaveBeenCalled();
    expect(await pendingCount()).toBe(1);
    const r = await syncNow();
    expect(r).toMatchObject({ online: false, stillQueued: 1 });
  });

  it("flushes every kind on reconnect with its stable Idempotency-Key", async () => {
    setOnline(false);
    withTokens(900);
    await fileIncident(INCIDENT_BODY);
    await fileStatement("case-1", { recorded_by: "u-1", party_type: "witness", statement_text: "saw it" });
    await fileArrest("case-1", { officer_id: "u-1", suspect_id: "sus-1", arrest_date: "x", location: null, legal_basis: null });
    const file = new File([new Uint8Array([9, 9, 9])], "g.png", { type: "image/png" });
    await fileEvidence("case-1", { case_id: "case-1", item_type: "photograph", description: "graffiti", collected_by: "u-1", collected_at: "x" }, file);

    const queued = await outboxAll();
    setOnline(true);
    submit.mockImplementation(async (row: OutboxItem) => ({ remoteId: `srv-${row.kind}` }));
    list.mockResolvedValue([
      { id: "c9", case_number: "CASE-9", incident_id: null, status: "open", lead_officer_id: "u-1", opened_at: "2026-09-07T09:00:00Z", closed_at: null },
    ]);

    const r = await syncNow();

    expect(submit).toHaveBeenCalledTimes(4);
    for (let i = 0; i < 4; i++) {
      const [row, token] = submit.mock.calls[i];
      expect(row.key).toBe(queued[i].key); // key stable across offline->online
      expect(typeof token).toBe("string");
    }
    // the evidence call still carried the file bytes
    const evCall = submit.mock.calls.find(([row]) => row.kind === "evidence")![0];
    expect(typeof evCall.fileB64).toBe("string");
    expect(atob(evCall.fileB64)).toBe(String.fromCharCode(9, 9, 9));

    expect(r).toMatchObject({ online: true, synced: 4, stillQueued: 0, casesUpdated: true });
    const rows = await outboxAll();
    expect(rows.every((x) => x.state === "synced")).toBe(true);
    // synced evidence row drops the file bytes to reclaim space
    expect(rows.find((x) => x.kind === "evidence")!.fileB64).toBeUndefined();
    expect((await getCases()).map((c) => c.id)).toEqual(["c9"]);
  });

  it("keeps a row queued + counts an attempt on a network failure", async () => {
    withTokens(900);
    await fileIncident(INCIDENT_BODY);
    submit.mockRejectedValue(new ApiError(0, "offline", { offline: true }));
    const r = await syncNow();
    expect(r.online).toBe(false);
    expect(r.synced).toBe(0);
    const row = (await outboxAll())[0];
    expect(row.state).toBe("queued");
    expect(row.attempts).toBe(1);
  });

  it("marks a 422 terminal and never retries it", async () => {
    withTokens(900);
    await fileStatement("case-1", { recorded_by: "u-1", party_type: "witness", statement_text: "" });
    submit.mockRejectedValue(new ApiError(422, "statement_text required"));
    const r1 = await syncNow();
    expect(r1.rejected).toBe(1);
    expect((await outboxAll())[0].state).toBe("rejected");
    submit.mockClear();
    await syncNow();
    expect(submit).not.toHaveBeenCalled();
  });

  it("refreshes an expired access token before flushing, then uses the new one", async () => {
    withTokens(-60);
    await fileIncident(INCIDENT_BODY);
    refresh.mockResolvedValue({ access_token: jwt(900), refresh_token: "opaque-refresh-2", token_type: "bearer", expires_in: 900 });
    submit.mockResolvedValue({ remoteId: "srv-1" });
    const r = await syncNow();
    expect(refresh).toHaveBeenCalledWith("opaque-refresh");
    expect(r.refreshed).toBe(true);
    expect(r.synced).toBe(1);
    expect(localStorage.getItem("pmp.field.refresh_token")).toBe("opaque-refresh-2");
    const [, token] = submit.mock.calls[0];
    expect(token).not.toBe("opaque-refresh");
  });

  it("surfaces needsReauth (dropping nothing) when the refresh token is rejected", async () => {
    withTokens(-60);
    await fileIncident(INCIDENT_BODY);
    refresh.mockRejectedValue(new ApiError(401, "refresh token expired"));
    const r = await syncNow();
    expect(r.needsReauth).toBe(true);
    expect(submit).not.toHaveBeenCalled();
    expect((await outboxAll())[0].state).toBe("queued");
  });
});
