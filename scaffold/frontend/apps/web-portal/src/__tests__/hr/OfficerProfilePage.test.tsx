import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { OfficerProfilePage } from "../../pages/hr/OfficerProfilePage";
import { ApiError, type Officer } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const getOfficer = vi.fn();
const updateOfficer = vi.fn();
const listAssignments = vi.fn();
const createAssignment = vi.fn();
const listTransfers = vi.fn();
const listLeave = vi.fn();
const listPromotions = vi.fn();
const listPerformance = vi.fn();
const listDiscipline = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    hr: {
      ...actual.hr,
      officers: { get: (...a: unknown[]) => getOfficer(...a), update: (...a: unknown[]) => updateOfficer(...a) },
      assignments: { list: (...a: unknown[]) => listAssignments(...a), create: (...a: unknown[]) => createAssignment(...a) },
      transfers: { forOfficer: (...a: unknown[]) => listTransfers(...a) },
      leave: { forOfficer: (...a: unknown[]) => listLeave(...a) },
      promotions: { list: (...a: unknown[]) => listPromotions(...a) },
      performance: { list: (...a: unknown[]) => listPerformance(...a) },
      discipline: { list: (...a: unknown[]) => listDiscipline(...a) },
    },
  };
});

function officer(over: Partial<Officer> = {}): Officer {
  return {
    id: "0ff-1",
    user_id: "u-1",
    badge_number: "OFF-100",
    rank: "Sergeant",
    unit_id: "unit-aaaaaaaa",
    hire_date: "2020-01-01",
    supervisor_id: null,
    status: "active",
    ...over,
  };
}

function renderPage(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "HR-1" }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/hr/officers/0ff-1"]}>
        <Routes>
          <Route path="/hr/officers/:officerId" element={<OfficerProfilePage />} />
          <Route path="/hr/officers" element={<div>directory</div>} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  [getOfficer, updateOfficer, listAssignments, createAssignment, listTransfers, listLeave, listPromotions, listPerformance, listDiscipline].forEach((m) => m.mockReset());
  getOfficer.mockResolvedValue(officer());
  listAssignments.mockResolvedValue([]);
  listTransfers.mockResolvedValue([]);
  listLeave.mockResolvedValue([]);
  listPromotions.mockResolvedValue([]);
  listPerformance.mockResolvedValue([]);
  listDiscipline.mockResolvedValue([]);
});

describe("OfficerProfilePage", () => {
  it("renders the officer header", async () => {
    renderPage(["hr.officer.read"]);
    expect(await screen.findByRole("heading", { name: "OFF-100" })).toBeInTheDocument();
    expect(screen.getByText(/Sergeant/)).toBeInTheDocument();
  });

  it("shows a 404 message for an unknown officer", async () => {
    getOfficer.mockRejectedValue(new ApiError(404, "No officer with that id"));
    renderPage(["hr.officer.read"]);
    expect(await screen.findByText(/no officer with that id/i)).toBeInTheDocument();
  });

  it("hides the discipline card without hr.discipline.read (UI RBAC, not just API)", async () => {
    renderPage(["hr.officer.read"]);
    await screen.findByRole("heading", { name: "OFF-100" });
    expect(screen.queryByRole("heading", { name: "Discipline records" })).not.toBeInTheDocument();
    expect(listDiscipline).not.toHaveBeenCalled();
  });

  it("shows the discipline card with hr.discipline.read", async () => {
    renderPage(["hr.officer.read", "hr.discipline.read"]);
    expect(await screen.findByRole("heading", { name: "Discipline records" })).toBeInTheDocument();
  });

  it("PATCHes only the changed fields", async () => {
    updateOfficer.mockResolvedValue(officer({ status: "suspended" }));
    const user = userEvent.setup();
    renderPage(["hr.officer.read", "hr.officer.write"]);
    await screen.findByRole("heading", { name: "OFF-100" });
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.selectOptions(screen.getByLabelText("Status"), "suspended");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(updateOfficer).toHaveBeenCalledWith("0ff-1", { status: "suspended" });
    expect(await screen.findByText("Profile updated.")).toBeInTheDocument();
  });

  it("does not offer the edit form without hr.officer.write", async () => {
    renderPage(["hr.officer.read"]);
    await screen.findByRole("heading", { name: "OFF-100" });
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("records an assignment and refetches", async () => {
    createAssignment.mockResolvedValue({ id: "a1", officer_id: "0ff-1", unit_id: "unit-x", start_date: "2026-02-01", end_date: null });
    const user = userEvent.setup();
    renderPage(["hr.officer.read", "hr.assignment.write"]);
    await screen.findByRole("heading", { name: "OFF-100" });
    await user.click(screen.getByRole("button", { name: "New assignment" }));
    await user.type(screen.getByLabelText("Unit id"), "unit-x");
    await user.type(screen.getByLabelText("Start date"), "2026-02-01");
    listAssignments.mockResolvedValue([{ id: "a1", officer_id: "0ff-1", unit_id: "unit-x", start_date: "2026-02-01", end_date: null }]);
    await user.click(screen.getByRole("button", { name: "Record" }));
    expect(createAssignment).toHaveBeenCalledWith("0ff-1", { unit_id: "unit-x", start_date: "2026-02-01" });
    expect(await screen.findByText("Assignment recorded.")).toBeInTheDocument();
  });
});
