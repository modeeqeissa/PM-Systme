import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CommandCenterPage } from "../../pages/command-center/CommandCenterPage";
import type { AdminRole, AdminUser } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    users: vi.fn(),
    createUser: vi.fn(),
    setStatus: vi.fn(),
    setRoles: vi.fn(),
    roles: vi.fn(),
    permissions: vi.fn(),
  },
}));
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, iamAdmin: mockApi };
});

const ROLES: AdminRole[] = [
  { id: 1, name: "ICT Admin", description: null, permissions: ["iam.user.write", "audit.read"] },
  { id: 2, name: "Patrol Officer", description: null, permissions: ["case.read", "case.write"] },
];

function user(over: Partial<AdminUser> = {}): AdminUser {
  return {
    id: "u-1",
    badge_number: "E2E-1",
    email: null,
    full_name: "Test One",
    station_id: "st-1",
    status: "active",
    failed_login_count: 0,
    mfa_enrolled: true,
    roles: [ROLES[1]],
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...over,
  };
}

function renderCC(perms: string[]) {
  setToken(fakeJwt({ permissions: perms }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/command-center?tab=users"]}>
        <Routes>
          <Route path="/command-center" element={<CommandCenterPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Command Center — Users & Roles (B4)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    Object.values(mockApi).forEach((f) => f.mockReset());
    mockApi.users.mockResolvedValue([user()]);
    mockApi.roles.mockResolvedValue(ROLES);
    mockApi.permissions.mockResolvedValue([
      { id: 1, code: "iam.user.write" },
      { id: 2, code: "case.read" },
      { id: 3, code: "case.write" },
      { id: 4, code: "audit.read" },
    ]);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("hides the tab and blocks the panel without iam.user.read", async () => {
    renderCC([]);
    expect(screen.queryByRole("button", { name: "Users & Roles" })).not.toBeInTheDocument();
    expect(await screen.findByText(/needs one of:/i)).toBeInTheDocument();
    expect(mockApi.users).not.toHaveBeenCalled();
  });

  it("lists users read-only for iam.user.read alone — no write actions", async () => {
    renderCC(["iam.user.read"]);
    expect(await screen.findByText("Test One")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New user" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit roles" })).not.toBeInTheDocument();
  });

  it("deactivate hits PATCH /users/{id} when the caller holds iam.user.write", async () => {
    mockApi.setStatus.mockResolvedValue(user({ status: "deactivated" }));
    renderCC(["iam.user.read", "iam.user.write"]);
    const row = (await screen.findByText("Test One")).closest("tr")!;
    await userEvent.setup().click(within(row).getByRole("button", { name: "Deactivate" }));
    expect(mockApi.setStatus).toHaveBeenCalledWith("u-1", "deactivated");
    expect(await screen.findByText(/deactivated — sessions revoked/i)).toBeInTheDocument();
  });

  it("role reassignment hits PUT /users/{id}/roles when the caller holds iam.role.write", async () => {
    mockApi.setRoles.mockResolvedValue({ id: "u-1", roles: ["ICT Admin"] });
    renderCC(["iam.user.read", "iam.role.write", "iam.role.read"]);
    const u = userEvent.setup();
    await screen.findByText("Test One");
    await u.click(screen.getByRole("button", { name: "Edit roles" }));
    await u.click(screen.getByLabelText("ICT Admin"));
    await u.click(screen.getByRole("button", { name: "Save roles" }));
    expect(mockApi.setRoles).toHaveBeenCalledWith("u-1", expect.arrayContaining([1, 2]));
  });

  it("renders the live role / permission matrix", async () => {
    renderCC(["iam.user.read", "iam.role.read"]);
    expect(await screen.findByText("Role / permission matrix · live from iam-service")).toBeInTheDocument();
    const permCell = await screen.findByText("iam.user.write");
    const matrixRow = permCell.closest("tr")!;
    // ICT Admin has it, Patrol Officer doesn't -> one dot, one middot
    expect(within(matrixRow).getAllByText("●").length).toBe(1);
  });
});
