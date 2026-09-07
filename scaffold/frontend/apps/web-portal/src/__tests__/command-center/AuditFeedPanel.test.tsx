import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CommandCenterPage } from "../../pages/command-center/CommandCenterPage";
import { ApiError, type AuditEntry } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const auditQuery = vi.fn();
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, audit: { query: (...a: unknown[]) => auditQuery(...a) } };
});

function entry(over: Partial<AuditEntry> = {}): AuditEntry {
  return {
    id: 42,
    service_name: "case-service",
    actor_id: "11111111-2222-3333-4444-555555555555",
    actor_role: "Investigator",
    entity_type: "case",
    entity_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    action: "create",
    timestamp: "2026-09-07T12:34:56.000Z",
    prev_hash: "0".repeat(64),
    record_hash: "abcdef0123456789".repeat(4),
    ...over,
  };
}

function renderCC(perms: string[], tab = "audit") {
  setToken(fakeJwt({ permissions: perms }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/command-center?tab=${tab}`]}>
        <Routes>
          <Route path="/command-center" element={<CommandCenterPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Command Center — Audit & Activity (B3)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    auditQuery.mockReset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("hides the tab and blocks the panel without audit.read", async () => {
    renderCC([]);
    expect(screen.queryByRole("button", { name: "Audit & Activity" })).not.toBeInTheDocument();
    expect(await screen.findByText(/needs one of:/i)).toBeInTheDocument();
    expect(auditQuery).not.toHaveBeenCalled();
  });

  it("lists entries from GET /audit for a caller with audit.read", async () => {
    auditQuery.mockResolvedValue([
      entry({ record_hash: "1".repeat(64) }),
      entry({ id: 41, action: "update", actor_role: "ICT Admin", record_hash: "2".repeat(64) }),
    ]);
    renderCC(["audit.read"]);
    // record_hash prefixes only appear in the table body, not the filter UI
    expect(await screen.findByText("111111111111…")).toBeInTheDocument();
    expect(screen.getByText("222222222222…")).toBeInTheDocument();
    expect(screen.getByText("Investigator")).toBeInTheDocument();
    expect(screen.getByText("ICT Admin")).toBeInTheDocument();
    expect(auditQuery).toHaveBeenCalledWith(expect.objectContaining({ limit: 50, offset: 0 }));
  });

  it("passes filters through to the query", async () => {
    auditQuery.mockResolvedValue([]);
    renderCC(["audit.read"]);
    await screen.findByText(/No audit entries match/i);

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Action"), "delete");
    await user.type(screen.getByLabelText("Entity type"), "evidence_item");
    await user.click(screen.getByRole("button", { name: "Apply" }));

    expect(auditQuery).toHaveBeenLastCalledWith(
      expect.objectContaining({ action: "delete", entity_type: "evidence_item", offset: 0 }),
    );
  });

  it("surfaces a 403 from audit-service", async () => {
    auditQuery.mockRejectedValue(new ApiError(403, "forbidden"));
    renderCC(["audit.read"]);
    expect(await screen.findByText(/can't read the audit log/i)).toBeInTheDocument();
  });
});
