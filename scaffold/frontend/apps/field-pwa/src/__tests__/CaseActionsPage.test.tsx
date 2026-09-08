import { IDBFactory } from "fake-indexeddb";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const fileStatement = vi.fn();
const fileArrest = vi.fn();
const fileEvidence = vi.fn();
const runQueuedWrite = vi.fn();
const personSearch = vi.fn();
const personCreate = vi.fn();

vi.mock("../lib/sync", () => ({
  fileStatement: (...a: unknown[]) => fileStatement(...a),
  fileArrest: (...a: unknown[]) => fileArrest(...a),
  fileEvidence: (...a: unknown[]) => fileEvidence(...a),
  runQueuedWrite: (...a: unknown[]) => runQueuedWrite(...a),
}));

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    persons: {
      search: (...a: unknown[]) => personSearch(...a),
      create: (...a: unknown[]) => personCreate(...a),
    },
  };
});

import { CaseActionsPage } from "../pages/CaseActionsPage";
import { _resetDbForTests, putCases } from "../lib/db";
import type { PersonRow } from "../lib/api";

function personRow(over: Partial<PersonRow> = {}): PersonRow {
  return {
    id: "per-1",
    first_name: "Awa",
    last_name: "Diop",
    date_of_birth: null,
    national_id: "NID-5",
    gender: null,
    address: null,
    phone: null,
    notes: null,
    created_at: "2026-09-01T00:00:00Z",
    ...over,
  };
}

function jwt(): string {
  const enc = (o: unknown) => btoa(JSON.stringify(o)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const now = Math.floor(Date.now() / 1000);
  return [enc({ alg: "RS256" }), enc({ sub: "off-1", station_id: "s-1", roles: [], permissions: [], iat: now, exp: now + 900 }), "sig"].join(".");
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/case/case-1"]}>
      <Routes>
        <Route path="/case/:caseId" element={<CaseActionsPage />} />
        <Route path="/" element={<div>cases</div>} />
        <Route path="/login" element={<div>login</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(async () => {
  globalThis.indexedDB = new IDBFactory();
  _resetDbForTests();
  localStorage.clear();
  localStorage.setItem("pmp.field.access_token", jwt());
  localStorage.setItem("pmp.field.refresh_token", "r");
  localStorage.setItem("pmp.field.tokens_obtained_at", String(Date.now()));
  [fileStatement, fileArrest, fileEvidence].forEach((m) => {
    m.mockReset();
    m.mockResolvedValue("local-1");
  });
  runQueuedWrite.mockReset();
  runQueuedWrite.mockImplementation(async (fn: () => Promise<string>) => {
    await fn();
    return { kind: "synced" };
  });
  personSearch.mockReset();
  personSearch.mockResolvedValue([]);
  personCreate.mockReset();
  await putCases([
    { id: "case-1", case_number: "CASE-2026-000042", incident_id: null, status: "open", lead_officer_id: "off-1", opened_at: "2026-09-01T00:00:00Z", closed_at: null },
  ]);
});

describe("CaseActionsPage", () => {
  it("shows the cached case number", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { name: "CASE-2026-000042" })).toBeInTheDocument();
  });

  it("queues a statement against this case with officer id from the token", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "CASE-2026-000042" });
    const addButtons = screen.getAllByRole("button", { name: "Add" });
    await user.click(addButtons[0]); // Record statement section

    await user.selectOptions(screen.getByLabelText("Party type"), "victim");
    await user.type(screen.getByLabelText("Statement"), "My bike was taken.");
    await user.click(screen.getByRole("button", { name: "Record statement" }));

    expect(fileStatement).toHaveBeenCalledWith("case-1", {
      recorded_by: "off-1",
      party_type: "victim",
      statement_text: "My bike was taken.",
    });
    expect(await screen.findByText(/Filed and synced to the server/i)).toBeInTheDocument();
  });

  it("queues an arrest against a person resolved by search", async () => {
    const user = userEvent.setup();
    personSearch.mockResolvedValue([personRow()]);
    renderPage();
    await screen.findByRole("heading", { name: "CASE-2026-000042" });
    await user.click(screen.getAllByRole("button", { name: "Add" })[1]); // Record arrest

    await user.type(screen.getByLabelText("Search people"), "diop");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.click(await screen.findByRole("button", { name: /Diop, Awa/ }));
    await user.click(screen.getByRole("button", { name: "Record arrest" }));

    expect(personSearch).toHaveBeenCalledWith(expect.any(String), "diop");
    expect(fileArrest).toHaveBeenCalledTimes(1);
    const [caseId, body] = fileArrest.mock.calls[0];
    expect(caseId).toBe("case-1");
    expect(body).toMatchObject({ officer_id: "off-1", suspect_id: "per-1" });
  });

  it("registers a new person and queues the arrest against them", async () => {
    const user = userEvent.setup();
    personCreate.mockResolvedValue(personRow({ id: "per-new", last_name: "Sy", first_name: "Bou" }));
    renderPage();
    await screen.findByRole("heading", { name: "CASE-2026-000042" });
    await user.click(screen.getAllByRole("button", { name: "Add" })[1]);

    await user.click(screen.getByRole("button", { name: "+ New person" }));
    await user.type(screen.getByLabelText("First name"), "Bou");
    await user.type(screen.getByLabelText("Last name"), "Sy");
    await user.click(screen.getByRole("button", { name: /Create & select/ }));
    await user.click(await screen.findByRole("button", { name: "Record arrest" }));

    expect(personCreate).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ first_name: "Bou", last_name: "Sy" }),
    );
    expect(fileArrest.mock.calls[0][1]).toMatchObject({ suspect_id: "per-new" });
  });

  it("blocks arrest recording while offline", async () => {
    const spy = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    try {
      const user = userEvent.setup();
      renderPage();
      await screen.findByRole("heading", { name: "CASE-2026-000042" });
      await user.click(screen.getAllByRole("button", { name: "Add" })[1]);
      expect(
        screen.getByText(/needs a connection to look up or register the person/i),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Record arrest" })).toBeDisabled();
    } finally {
      spy.mockRestore();
    }
  });

  it("queues an evidence item with the selected file as a blob", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "CASE-2026-000042" });
    const addButtons = screen.getAllByRole("button", { name: "Add" });
    await user.click(addButtons[2]); // Log evidence section

    await user.type(screen.getByLabelText("Item type"), "photograph");
    await user.type(screen.getByLabelText("Description"), "graffiti on the shelter");
    const file = new File([new Uint8Array([1, 2, 3, 4])], "graffiti.png", { type: "image/png" });
    await user.upload(screen.getByLabelText(/Photo \/ file/i), file);
    await user.click(screen.getByRole("button", { name: "Log evidence" }));

    expect(fileEvidence).toHaveBeenCalledTimes(1);
    const [caseId, body, uploaded] = fileEvidence.mock.calls[0];
    expect(caseId).toBe("case-1");
    expect(body).toMatchObject({ case_id: "case-1", item_type: "photograph", collected_by: "off-1" });
    expect(uploaded).toBeInstanceOf(File);
    expect(uploaded.name).toBe("graffiti.png");
  });
});
