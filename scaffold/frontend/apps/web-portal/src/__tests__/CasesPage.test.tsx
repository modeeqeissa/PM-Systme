import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CasesPage } from "../pages/CasesPage";
import { ApiError, type Case } from "../lib/api";
import { setToken } from "../lib/auth";
import { fakeJwt } from "../test/jwt";

const list = vi.fn();

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, cases: { list: (...a: unknown[]) => list(...a) } };
});

function renderCases() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/cases"]}>
        <Routes>
          <Route path="/cases" element={<CasesPage />} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const row = (over: Partial<Case> = {}): Case => ({
  id: crypto.randomUUID(),
  case_number: "CASE-2026-000001",
  incident_id: null,
  status: "open",
  lead_officer_id: "u-1",
  opened_at: "2026-09-04T09:00:00Z",
  closed_at: null,
  ...over,
});

beforeEach(() => {
  list.mockReset();
  setToken(fakeJwt({ sub: "u-1", badge_number: "OFF-1", roles: ["Investigator"] }));
});

describe("CasesPage", () => {
  it("renders case number, status and lead officer for each row", async () => {
    list.mockResolvedValue([
      row({ case_number: "CASE-2026-000007", status: "investigating", lead_officer_id: "u-1" }),
      row({ case_number: "CASE-2026-000008", status: "closed", lead_officer_id: "someone-else-9999" }),
    ]);

    renderCases();

    expect(await screen.findByText("CASE-2026-000007")).toBeInTheDocument();
    expect(screen.getByText("Investigating")).toBeInTheDocument();
    expect(screen.getByText("You (OFF-1)")).toBeInTheDocument(); // lead_officer_id === sub

    expect(screen.getByText("CASE-2026-000008")).toBeInTheDocument();
    expect(screen.getByText("Closed")).toBeInTheDocument();
    expect(screen.getByText("someone-…")).toBeInTheDocument();
  });

  it("shows an empty state when the caller can see no cases", async () => {
    list.mockResolvedValue([]);
    renderCases();
    expect(await screen.findByText(/no cases visible to you/i)).toBeInTheDocument();
  });

  it("explains a 403 (missing case.read)", async () => {
    list.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
    renderCases();
    expect(await screen.findByRole("alert")).toHaveTextContent(/can't view cases/i);
  });

  it("redirects to /login on a 401", async () => {
    list.mockRejectedValue(new ApiError(401, "expired"));
    renderCases();
    expect(await screen.findByText("login screen")).toBeInTheDocument();
  });
});
