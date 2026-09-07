import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const fileIncident = vi.fn();
const runQueuedWrite = vi.fn();

vi.mock("../lib/sync", () => ({
  fileIncident: (...a: unknown[]) => fileIncident(...a),
  runQueuedWrite: (...a: unknown[]) => runQueuedWrite(...a),
}));

import { FileIncidentPage } from "../pages/FileIncidentPage";

function jwt(): string {
  const enc = (o: unknown) => btoa(JSON.stringify(o)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
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

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("pmp.field.access_token", jwt());
  localStorage.setItem("pmp.field.refresh_token", "r");
  localStorage.setItem("pmp.field.tokens_obtained_at", String(Date.now()));
  fileIncident.mockReset();
  runQueuedWrite.mockReset();
  fileIncident.mockResolvedValue("local-1");
});

async function fill(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Incident type"), "theft");
  await user.type(screen.getByLabelText("What happened"), "bike gone from the rack");
  await user.click(screen.getByRole("button", { name: "File incident" }));
}

describe("FileIncidentPage", () => {
  it("queues the incident with fields from the form + token, and shows the synced result", async () => {
    const user = userEvent.setup();
    runQueuedWrite.mockImplementation(async (fn: () => Promise<string>) => {
      await fn();
      return { kind: "synced" };
    });
    renderPage();
    await fill(user);
    expect(await screen.findByText(/Filed and synced to the server/i)).toBeInTheDocument();
    const [body] = fileIncident.mock.calls[0];
    expect(body).toMatchObject({ reported_by: "u-1", incident_type: "theft", station_id: "s-1" });
  });

  it("shows the 'saved on device' message when the write only queued", async () => {
    const user = userEvent.setup();
    runQueuedWrite.mockResolvedValue({ kind: "queued" });
    renderPage();
    await fill(user);
    expect(await screen.findByText(/Saved on this device\. It will sync/i)).toBeInTheDocument();
  });

  it("surfaces a server rejection without claiming it was filed", async () => {
    const user = userEvent.setup();
    runQueuedWrite.mockResolvedValue({ kind: "rejected", detail: "422 station_id required" });
    renderPage();
    await fill(user);
    expect(await screen.findByText(/server rejected this incident/i)).toBeInTheDocument();
  });

  it("surfaces an out-of-storage failure", async () => {
    const user = userEvent.setup();
    runQueuedWrite.mockResolvedValue({ kind: "quota" });
    renderPage();
    await fill(user);
    expect(await screen.findByText(/out of storage/i)).toBeInTheDocument();
  });
});
