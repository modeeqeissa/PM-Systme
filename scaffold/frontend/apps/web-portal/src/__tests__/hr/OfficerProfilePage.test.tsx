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
const listAttendance = vi.fn();
const recordAttendance = vi.fn();
const updateAttendance = vi.fn();
const listAwards = vi.fn();
const recordAward = vi.fn();

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
      attendance: {
        forOfficer: (...a: unknown[]) => listAttendance(...a),
        record: (...a: unknown[]) => recordAttendance(...a),
        update: (...a: unknown[]) => updateAttendance(...a),
      },
      awards: {
        forOfficer: (...a: unknown[]) => listAwards(...a),
        record: (...a: unknown[]) => recordAward(...a),
      },
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
  [
    getOfficer, updateOfficer, listAssignments, createAssignment, listTransfers, listLeave,
    listPromotions, listPerformance, listDiscipline, listAttendance, recordAttendance,
    updateAttendance, listAwards, recordAward,
  ].forEach((m) => m.mockReset());
  getOfficer.mockResolvedValue(officer());
  listAssignments.mockResolvedValue([]);
  listTransfers.mockResolvedValue([]);
  listLeave.mockResolvedValue([]);
  listPromotions.mockResolvedValue([]);
  listPerformance.mockResolvedValue([]);
  listDiscipline.mockResolvedValue([]);
  listAttendance.mockResolvedValue([]);
  listAwards.mockResolvedValue([]);
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

  it("hides Attendance and Awards cards without their read permissions", async () => {
    renderPage(["hr.officer.read"]);
    await screen.findByRole("heading", { name: "OFF-100" });
    expect(screen.queryByRole("heading", { name: "Attendance" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Awards & commendations" })).not.toBeInTheDocument();
  });

  it("records a day of attendance and refetches", async () => {
    recordAttendance.mockResolvedValue({
      id: "at1", officer_id: "0ff-1", date: "2026-09-01", clock_in: null, clock_out: null, status: "late",
    });
    const user = userEvent.setup();
    renderPage(["hr.officer.read", "hr.attendance.read", "hr.attendance.write"]);
    await screen.findByRole("heading", { name: "Attendance" });

    await user.click(screen.getByRole("button", { name: "Record day" }));
    await user.type(screen.getByLabelText("Date"), "2026-09-01");
    await user.selectOptions(screen.getByLabelText("Status"), "late");
    listAttendance.mockResolvedValue([
      { id: "at1", officer_id: "0ff-1", date: "2026-09-01", clock_in: null, clock_out: null, status: "late" },
    ]);
    await user.click(screen.getByRole("button", { name: "Record" }));

    expect(recordAttendance).toHaveBeenCalledWith("0ff-1", { date: "2026-09-01", status: "late" });
    expect(await screen.findByText("Attendance recorded.")).toBeInTheDocument();
    // the row rendered (date + a "mark absent" action for a non-absent row)
    expect(await screen.findByText("2026-09-01")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "mark absent" })).toBeInTheDocument();
  });

  it("records an award (optional fields sent as null) and shows it", async () => {
    recordAward.mockResolvedValue({
      id: "aw1", officer_id: "0ff-1", title: "Commendation for Bravery", description: null,
      awarded_date: "2026-08-01", awarded_by: null,
    });
    const user = userEvent.setup();
    renderPage(["hr.officer.read", "hr.award.read", "hr.award.write"]);
    await screen.findByRole("heading", { name: "Awards & commendations" });

    await user.click(screen.getByRole("button", { name: "Record award" }));
    await user.type(screen.getByLabelText("Title"), "Commendation for Bravery");
    await user.type(screen.getByLabelText("Awarded date"), "2026-08-01");
    listAwards.mockResolvedValue([
      { id: "aw1", officer_id: "0ff-1", title: "Commendation for Bravery", description: null, awarded_date: "2026-08-01", awarded_by: null },
    ]);
    await user.click(screen.getByRole("button", { name: "Record" }));

    expect(recordAward).toHaveBeenCalledWith("0ff-1", {
      title: "Commendation for Bravery",
      description: null,
      awarded_date: "2026-08-01",
      awarded_by: null,
    });
    expect(await screen.findByText("Commendation for Bravery")).toBeInTheDocument();
  });
});
