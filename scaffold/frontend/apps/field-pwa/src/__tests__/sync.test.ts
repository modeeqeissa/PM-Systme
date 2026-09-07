import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it, vi } from "vitest";

const create = vi.fn();
const list = vi.fn();
const refresh = vi.fn();

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    iam: { ...actual.iam, refresh: (...a: unknown[]) => refresh(...a) },
    cases: { list: (...a: unknown[]) => list(...a) },
    incidents: { create: (...a: unknown[]) => create(...a) },
  };
});

import { ApiError, type IncidentInput } from "../lib/api";
import { _resetDbForTests, outboxAll, pendingCount, getCases } from "../lib/db";
import { fileIncident, syncNow } from "../lib/sync";

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

const BODY: IncidentInput = {
  reported_by: "u-1",
  incident_type: "theft",
  description: "bike gone from the rack",
  station_id: "s-1",
  reported_at: "2026-09-07T08:00:00.000Z",
};

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory();
  _resetDbForTests();
  localStorage.clear();
  create.mockReset();
  list.mockReset();
  refresh.mockReset();
  list.mockResolvedValue([]);
  setOnline(true);
});

describe("offline-sync engine", () => {
  it("queues an incident when offline and posts nothing", async () => {
    setOnline(false);
    withTokens(900);

    await fileIncident(BODY);

    expect(create).not.toHaveBeenCalled();
    expect(await pendingCount()).toBe(1);
    const r = await syncNow();
    expect(r.online).toBe(false);
    expect(r.stillQueued).toBe(1);
  });

  it("flushes the queue on reconnect with the SAME idempotency key, then refreshes the cache", async () => {
    setOnline(false);
    withTokens(900);
    await fileIncident(BODY);
    const queued = (await outboxAll())[0];

    setOnline(true);
    create.mockResolvedValue({ incident: { id: "srv-1" }, replayed: false });
    list.mockResolvedValue([
      { id: "srv-1c", case_number: "CASE-9", incident_id: "srv-1", status: "open", lead_officer_id: "u-1", opened_at: "2026-09-07T09:00:00Z", closed_at: null },
    ]);

    const r = await syncNow();

    expect(create).toHaveBeenCalledTimes(1);
    const [body, key, token] = create.mock.calls[0];
    expect(body).toEqual(BODY);
    expect(key).toBe(queued.key); // stable key across the offline->online boundary
    expect(typeof token).toBe("string");

    expect(r).toMatchObject({ online: true, synced: 1, stillQueued: 0, casesUpdated: true });
    const row = (await outboxAll())[0];
    expect(row.state).toBe("synced");
    expect(row.remoteId).toBe("srv-1");
    expect((await getCases()).map((c) => c.id)).toEqual(["srv-1c"]);
  });

  it("treats a 200 replay (server already had the key) as synced", async () => {
    withTokens(900);
    await fileIncident(BODY);
    create.mockResolvedValue({ incident: { id: "srv-1" }, replayed: true });

    const r = await syncNow();
    expect(r.synced).toBe(1);
    expect((await outboxAll())[0].state).toBe("synced");
  });

  it("keeps the row queued and counts an attempt on a network failure mid-flush", async () => {
    withTokens(900);
    await fileIncident(BODY);
    create.mockRejectedValue(new ApiError(0, "offline", { offline: true }));

    const r = await syncNow();
    expect(r.online).toBe(false);
    expect(r.synced).toBe(0);
    const row = (await outboxAll())[0];
    expect(row.state).toBe("queued");
    expect(row.attempts).toBe(1);
  });

  it("marks a 422 rejection terminal and never retries it", async () => {
    withTokens(900);
    await fileIncident(BODY);
    create.mockRejectedValue(new ApiError(422, "station_id required"));

    const r1 = await syncNow();
    expect(r1.rejected).toBe(1);
    expect((await outboxAll())[0].state).toBe("rejected");

    create.mockClear();
    const r2 = await syncNow();
    expect(create).not.toHaveBeenCalled(); // rejected rows are not re-sent
    expect(r2.synced).toBe(0);
  });

  it("refreshes an expired access token before flushing, then uses the new one", async () => {
    withTokens(-60); // access token already expired
    await fileIncident(BODY);
    refresh.mockResolvedValue({
      access_token: jwt(900),
      refresh_token: "opaque-refresh-2",
      token_type: "bearer",
      expires_in: 900,
    });
    create.mockResolvedValue({ incident: { id: "srv-2" }, replayed: false });

    const r = await syncNow();

    expect(refresh).toHaveBeenCalledWith("opaque-refresh");
    expect(r.refreshed).toBe(true);
    expect(r.synced).toBe(1);
    // the token handed to create is the refreshed one
    const [, , token] = create.mock.calls[0];
    expect(token).not.toBe("opaque-refresh");
    expect(localStorage.getItem("pmp.field.refresh_token")).toBe("opaque-refresh-2");
  });

  it("surfaces needsReauth (dropping nothing) when the refresh token is rejected", async () => {
    withTokens(-60);
    await fileIncident(BODY);
    refresh.mockRejectedValue(new ApiError(401, "refresh token expired"));

    const r = await syncNow();
    expect(r.needsReauth).toBe(true);
    expect(create).not.toHaveBeenCalled();
    expect((await outboxAll())[0].state).toBe("queued"); // still safe on the device
  });
});
