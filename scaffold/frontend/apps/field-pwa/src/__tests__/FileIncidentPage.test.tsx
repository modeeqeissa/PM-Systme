import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const fileIncident = vi.fn();
const syncNow = vi.fn();

vi.mock("../lib/sync", () => ({
  fileIncident: (...a: unknown[]) => fileIncident(...a),
  syncNow: (...a: unknown[]) => syncNow(...a),
}));

import { FileIncidentPage } from "../pages/FileIncidentPage";
import { enqueueIncident, _resetDbForTests, type OutboxIncident } from "../lib/db";

function jwt(): string {
  const enc = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const now = Math.floor(Date.now() / 1000);
  return [enc({ alg: "RS256" }), enc({ sub: "u-1", station_id: "s-1", roles: [], permissions: [], iat: now, exp: now + 900 }), "sig"].join(".");
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/incident"]}>
      <Routes>
        <Route path="/incident" element={<FileIncidentPage />} />
        <Route path="/" element={<div>cases</div>} />
        <Route path="/login" element={<div>login</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const row = (over: Partial<OutboxIncident>): OutboxIncident => ({
  id: "local-1",
  key: "key-1",
  body: { reported_by: "u-1", incident_type: "theft", description: "x", station_id: "s-1", reported_at: "2026-09-07T08:00:00.000Z" },
  state: "queued",
  attempts: 0,
  createdAt: Date.now(),
  ...over,
});

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory();
  _resetDbForTests();
  localStorage.clear();
  localStorage.setItem("pmp.field.access_token", jwt());
  localStorage.setItem("pmp.field.refresh_token", "r");
  localStorage.setItem("pmp.field.tokens_obtained_at", String(Date.now()));
  fileIncident.mockReset();
  syncNow.mockReset();
});

async function fill(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Incident type"), "theft");
  await user.type(screen.getByLabelText("What happened"), "bike gone from the rack");
  await user.click(screen.getByRole("button", { name: "File incident" }));
}

describe("FileIncidentPage", () => {
  it("shows a 'synced' confirmation when the queued incident reached the server", async () => {
    const user = userEvent.setup();
    fileIncident.mockImplementation(async () => {
      await enqueueIncident(row({ state: "synced", remoteId: "srv-1" }));
      return "local-1";
    });
    syncNow.mockResolvedValue({ needsReauth: false, online: true, synced: 1 });
    renderPage();
    await fill(user);
    expect(await screen.findByText(/Filed and synced to case-service/i)).toBeInTheDocument();
    const [body] = fileIncident.mock.calls[0];
    expect(body).toMatchObject({ reported_by: "u-1", incident_type: "theft", station_id: "s-1" });
  });

  it("shows a 'saved on device' message when offline / still queued", async () => {
    const user = userEvent.setup();
    fileIncident.mockImplementation(async () => {
      await enqueueIncident(row({ state: "queued" }));
      return "local-1";
    });
    syncNow.mockResolvedValue({ needsReauth: false, online: false, synced: 0 });
    renderPage();
    await fill(user);
    expect(await screen.findByText(/Saved on this device\. It will sync/i)).toBeInTheDocument();
  });

  it("surfaces a server rejection without claiming it was filed", async () => {
    const user = userEvent.setup();
    fileIncident.mockImplementation(async () => {
      await enqueueIncident(row({ state: "rejected", lastError: "422 station_id required" }));
      return "local-1";
    });
    syncNow.mockResolvedValue({ needsReauth: false, online: true, synced: 0, rejected: 1 });
    renderPage();
    await fill(user);
    expect(await screen.findByText(/server rejected this incident/i)).toBeInTheDocument();
  });
});
