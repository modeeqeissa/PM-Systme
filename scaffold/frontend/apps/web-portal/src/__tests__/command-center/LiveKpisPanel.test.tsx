import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CommandCenterPage } from "../../pages/command-center/CommandCenterPage";
import { ApiError, type KpiSnapshot } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";
import { currentMonthRange } from "../../lib/datetime";

const kpis = vi.fn();
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, dashboard: { kpis: (...a: unknown[]) => kpis(...a) } };
});

const MONTH = currentMonthRange().from;

function snapshot(over: Partial<KpiSnapshot> = {}): KpiSnapshot {
  return {
    station_id: "st-1",
    as_of: "2026-09-05T10:00:00Z",
    cases: { opened: 5, closed: 2, arrests_recorded: 1, avg_case_age_days: 4 },
    crime_trends: [{ month: MONTH, incident_type: "burglary", count: 3 }],
    evidence_integrity: { evidence_logged: 3, pending_transfer_ack: 0, hash_mismatches: 1 },
    unit_readiness: [],
    ...over,
  };
}

function renderCC(perms: string[], tab = "kpis") {
  setToken(fakeJwt({ permissions: perms, station_id: "st-1" }));
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

describe("Command Center — Live KPIs (B2)", () => {
  beforeEach(() => {
    // System Health tab always mounts; keep its /health polling quiet.
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    kpis.mockReset();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("hides the KPIs tab and blocks the panel without dashboard.view", async () => {
    renderCC([]); // no perms
    expect(screen.queryByRole("button", { name: "Live KPIs" })).not.toBeInTheDocument();
    // deep-linked ?tab=kpis still renders the not-authorised notice
    expect(await screen.findByText(/needs one of:/i)).toBeInTheDocument();
    expect(kpis).not.toHaveBeenCalled();
  });

  it("renders the dashboard read models when the caller holds dashboard.view", async () => {
    kpis.mockResolvedValue(snapshot());
    renderCC(["dashboard.view"]);
    expect(await screen.findByRole("button", { name: "Live KPIs" })).toBeInTheDocument();
    expect(await screen.findByText("Cases")).toBeInTheDocument();
    expect(await screen.findByText("5")).toBeInTheDocument(); // opened
    expect(await screen.findByText("Evidence integrity")).toBeInTheDocument();
    expect(await screen.findByText("burglary")).toBeInTheDocument();
    expect(kpis).toHaveBeenCalled();
  });

  it("surfaces a 403 from dashboard-service", async () => {
    kpis.mockRejectedValue(new ApiError(403, "forbidden"));
    renderCC(["dashboard.view"]);
    expect(await screen.findByText(/can't view KPIs/i)).toBeInTheDocument();
  });
});
