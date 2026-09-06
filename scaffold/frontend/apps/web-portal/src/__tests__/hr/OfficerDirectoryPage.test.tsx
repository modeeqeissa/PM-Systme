import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { OfficerDirectoryPage } from "../../pages/hr/OfficerDirectoryPage";
import { ApiError, type Officer } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const listOfficers = vi.fn();
const createOfficer = vi.fn();
const listUnits = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    hr: {
      ...actual.hr,
      officers: { list: (...a: unknown[]) => listOfficers(...a), create: (...a: unknown[]) => createOfficer(...a) },
      units: { list: (...a: unknown[]) => listUnits(...a) },
    },
  };
});

function officer(over: Partial<Officer> = {}): Officer {
  return {
    id: "0ff-1",
    user_id: "u-1",
    badge_number: "OFF-100",
    rank: "Sergeant",
    unit_id: "unit-aaaaaaaa-0000-0000-0000-000000000000",
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
      <MemoryRouter initialEntries={["/hr/officers"]}>
        <Routes>
          <Route path="/hr/officers" element={<OfficerDirectoryPage />} />
          <Route path="/hr/officers/:officerId" element={<div>profile screen</div>} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listOfficers.mockReset();
  createOfficer.mockReset();
  listUnits.mockReset();
  listUnits.mockResolvedValue([]);
  listOfficers.mockResolvedValue([]);
});

describe("OfficerDirectoryPage", () => {
  it("lists officers and links each to its profile", async () => {
    listOfficers.mockResolvedValue([officer(), officer({ id: "0ff-2", badge_number: "OFF-200", rank: "Constable" })]);
    renderPage(["hr.officer.read"]);
    expect(await screen.findByRole("link", { name: "OFF-100" })).toHaveAttribute("href", "/hr/officers/0ff-1");
    expect(screen.getByRole("link", { name: "OFF-200" })).toBeInTheDocument();
  });

  it("filters by status via the API query", async () => {
    listOfficers.mockResolvedValue([officer()]);
    const user = userEvent.setup();
    renderPage(["hr.officer.read"]);
    await screen.findByRole("link", { name: "OFF-100" });
    await user.selectOptions(screen.getByLabelText("Status"), "suspended");
    // last call carries the status filter
    const lastArgs = listOfficers.mock.calls.at(-1)![0];
    expect(lastArgs).toMatchObject({ status: "suspended" });
  });

  it("searches the loaded page by badge, client-side", async () => {
    listOfficers.mockResolvedValue([
      officer({ badge_number: "OFF-100" }),
      officer({ id: "0ff-2", badge_number: "ZZZ-999" }),
    ]);
    const user = userEvent.setup();
    renderPage(["hr.officer.read"]);
    await screen.findByRole("link", { name: "OFF-100" });
    await user.type(screen.getByLabelText("Search"), "zzz");
    expect(screen.queryByRole("link", { name: "OFF-100" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ZZZ-999" })).toBeInTheDocument();
  });

  it("hides the New officer form without hr.officer.write", async () => {
    renderPage(["hr.officer.read"]);
    await screen.findByText(/no officers match/i);
    expect(screen.queryByRole("button", { name: "Add officer" })).not.toBeInTheDocument();
  });

  it("creates an officer and refetches when hr.officer.write is held", async () => {
    createOfficer.mockResolvedValue(officer({ id: "new-1", badge_number: "OFF-777" }));
    const user = userEvent.setup();
    renderPage(["hr.officer.read", "hr.officer.write"]);
    await screen.findByText(/no officers match/i);
    await user.click(screen.getByRole("button", { name: "Add officer" }));
    await user.type(screen.getByLabelText("User id"), "u-9");
    await user.type(screen.getByLabelText("Badge number"), "OFF-777");
    await user.type(screen.getByLabelText("Rank"), "Constable");
    await user.type(screen.getByLabelText("Unit id"), "unit-9");
    await user.type(screen.getByLabelText("Hire date"), "2026-01-02");
    listOfficers.mockResolvedValue([officer({ id: "new-1", badge_number: "OFF-777" })]);
    await user.click(screen.getByRole("button", { name: "Create officer" }));

    expect(createOfficer).toHaveBeenCalledWith({
      user_id: "u-9",
      badge_number: "OFF-777",
      rank: "Constable",
      unit_id: "unit-9",
      hire_date: "2026-01-02",
    });
    expect(await screen.findByText(/Created officer/i)).toBeInTheDocument();
  });

  it("surfaces a 403 on the officer list", async () => {
    listOfficers.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
    renderPage(["hr.officer.read"]);
    expect(await screen.findByText(/can't view officers/i)).toBeInTheDocument();
  });

  it("surfaces 422 field errors on create", async () => {
    createOfficer.mockRejectedValue(
      new ApiError(422, "Unprocessable", {
        detail: [{ loc: ["body", "badge_number"], msg: "already in use", type: "x" }],
      }),
    );
    const user = userEvent.setup();
    renderPage(["hr.officer.read", "hr.officer.write"]);
    await screen.findByText(/no officers match/i);
    await user.click(screen.getByRole("button", { name: "Add officer" }));
    await user.type(screen.getByLabelText("User id"), "u-9");
    await user.type(screen.getByLabelText("Badge number"), "OFF-1");
    await user.type(screen.getByLabelText("Rank"), "Constable");
    await user.type(screen.getByLabelText("Unit id"), "unit-9");
    await user.type(screen.getByLabelText("Hire date"), "2026-01-02");
    await user.click(screen.getByRole("button", { name: "Create officer" }));
    expect(await screen.findByText("already in use")).toBeInTheDocument();
  });
});
