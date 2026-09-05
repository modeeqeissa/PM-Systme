import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DashboardPage } from "../pages/DashboardPage";
import { ApiError, type KpiSnapshot } from "../lib/api";
import { setToken } from "../lib/auth";
import { fakeJwt } from "../test/jwt";
import { currentMonthRange } from "../lib/datetime";

const kpis = vi.fn();

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, dashboard: { kpis: (...a: unknown[]) => kpis(...a) } };
});

const STATION = "6b1df6ad-bdf5-4637-9f08-bb85ddc93eca";
const MONTH = currentMonthRange().from; // e.g. "2026-09-01"

function snapshot(over: Partial<KpiSnapshot> = {}): KpiSnapshot {
  return {
    station_id: STATION,
    as_of: "2026-09-05T10:00:00Z",
    cases: { opened: 1, closed: 0, arrests_recorded: 0, avg_case_age_days: null },
    crime_trends: [
      { month: MONTH, incident_type: "burglary", count: 1 },
      { month: MONTH, incident_type: "theft", count: 3 },
    ],
    evidence_integrity: { evidence_logged: 0, pending_transfer_ack: 0, hash_mismatches: 0 },
    unit_readiness: [],
    ...over,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  kpis.mockReset();
  setToken(fakeJwt({ station_id: STATION, roles: ["Station Commander"], badge_number: "CMD-1" }));
});

describe("DashboardPage", () => {
  it("defaults the query to the caller's station and the current month", async () => {
    kpis.mockResolvedValue(snapshot());
    renderPage();
    await screen.findByRole("heading", { name: "Cases" });
    const { from, to } = currentMonthRange();
    expect(kpis).toHaveBeenCalledWith({ station_id: STATION, from, to });
  });

  it("renders the KPI shape: open/closed counts and crime-trend rows", async () => {
    kpis.mockResolvedValue(snapshot());
    renderPage();

    const casesCard = (await screen.findByRole("heading", { name: "Cases" })).closest("div")!;
    expect(within(casesCard).getByText("Open")).toBeInTheDocument();
    expect(within(casesCard).getByText("Open").previousElementSibling).toHaveTextContent("1");
    expect(within(casesCard).getByText("Closed")).toBeInTheDocument();
    expect(within(casesCard).getByText("Closed").previousElementSibling).toHaveTextContent("0");

    const trendCard = screen.getByRole("heading", { name: "Crime trend by type" }).closest("div")!;
    const rows = within(trendCard).getAllByRole("listitem");
    // sorted by count desc: theft (3) before burglary (1)
    expect(rows[0]).toHaveTextContent("theft");
    expect(rows[0]).toHaveTextContent("3");
    expect(rows[1]).toHaveTextContent("burglary");
    expect(rows[1]).toHaveTextContent("1");
  });

  it("renders arrests_recorded and avg_case_age_days in the Cases card", async () => {
    kpis.mockResolvedValue(
      snapshot({ cases: { opened: 2, closed: 1, arrests_recorded: 3, avg_case_age_days: 4.5 } }),
    );
    renderPage();

    const casesCard = (await screen.findByRole("heading", { name: "Cases" })).closest("div")!;
    expect(within(casesCard).getByText("Arrests recorded")).toBeInTheDocument();
    expect(within(casesCard).getByText("3")).toBeInTheDocument();
    expect(within(casesCard).getByText("Avg case age (days)")).toBeInTheDocument();
    expect(within(casesCard).getByText("4.5")).toBeInTheDocument();
  });

  it("shows a placeholder for a null avg_case_age_days (no closed cases yet)", async () => {
    kpis.mockResolvedValue(
      snapshot({ cases: { opened: 1, closed: 0, arrests_recorded: 0, avg_case_age_days: null } }),
    );
    renderPage();

    const casesCard = (await screen.findByRole("heading", { name: "Cases" })).closest("div")!;
    expect(within(casesCard).getByText("Avg case age (days)")).toBeInTheDocument();
    expect(within(casesCard).getByText("—")).toBeInTheDocument();
  });

  it("shows an empty crime-trend message when there are no buckets this month", async () => {
    kpis.mockResolvedValue(snapshot({ crime_trends: [] }));
    renderPage();
    expect(
      await screen.findByText(/no incidents recorded for this window/i),
    ).toBeInTheDocument();
  });

  it("labels a null incident_type bucket as (unspecified)", async () => {
    kpis.mockResolvedValue(
      snapshot({ crime_trends: [{ month: MONTH, incident_type: null, count: 4 }] }),
    );
    renderPage();
    expect(await screen.findByText("(unspecified)")).toBeInTheDocument();
  });

  it("renders the evidence integrity KPIs, highlighting hash mismatches", async () => {
    kpis.mockResolvedValue(
      snapshot({
        evidence_integrity: {
          evidence_logged: 4,
          pending_transfer_ack: 1,
          hash_mismatches: 2,
        },
      }),
    );
    renderPage();

    const card = (
      await screen.findByRole("heading", { name: "Evidence integrity" })
    ).closest("div")!;
    expect(within(card).getByText("4")).toBeInTheDocument();
    expect(within(card).getByText("Evidence logged")).toBeInTheDocument();
    expect(within(card).getByText("1")).toBeInTheDocument();
    expect(within(card).getByText("Pending transfer ack")).toBeInTheDocument();
    const mismatchCount = within(card).getByText("2");
    expect(mismatchCount).toBeInTheDocument();
    expect(mismatchCount).toHaveClass("text-rose-600");
  });

  it("shows a zero hash-mismatch count without the warning color", async () => {
    kpis.mockResolvedValue(snapshot());
    renderPage();
    await screen.findByRole("heading", { name: "Evidence integrity" });
    const label = screen.getByText("Hash mismatches");
    const mismatchCount = label.previousElementSibling!;
    expect(mismatchCount).toHaveTextContent("0");
    expect(mismatchCount).not.toHaveClass("text-rose-600");
  });

  it("explains a 403 (missing dashboard.view)", async () => {
    kpis.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(/can't view the dashboard/i);
    expect(screen.getByText(/dashboard\.view/)).toBeInTheDocument();
  });

  it("redirects to /login on a 401", async () => {
    kpis.mockRejectedValue(new ApiError(401, "expired"));
    renderPage();
    expect(await screen.findByText("login screen")).toBeInTheDocument();
  });
});
