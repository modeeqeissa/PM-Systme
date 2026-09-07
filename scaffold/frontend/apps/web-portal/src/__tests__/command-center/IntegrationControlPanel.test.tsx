import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CommandCenterPage } from "../../pages/command-center/CommandCenterPage";
import { ApiError, type ExternalSystemLog, type IntegrationConfig } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const { mockInt } = vi.hoisted(() => ({
  mockInt: { configs: vi.fn(), setEnabled: vi.fn(), logs: vi.fn() },
}));
vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, integration: mockInt };
});

const CONFIGS: IntegrationConfig[] = [
  { id: 1, system_name: "CAD", enabled: true },
  { id: 2, system_name: "NCDB", enabled: false },
  { id: 3, system_name: "COURTS", enabled: true },
  { id: 4, system_name: "JAIL", enabled: true },
];
const LOGS: ExternalSystemLog[] = [
  { id: 9, system_name: "CAD", direction: "outbound", correlation_id: "abcd1234-0000-0000-0000-000000000000", response_status: 200 },
  { id: 8, system_name: "NCDB", direction: "outbound", correlation_id: "ef567890-0000-0000-0000-000000000000", response_status: 409 },
];

function renderCC(perms: string[]) {
  setToken(fakeJwt({ permissions: perms }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/command-center?tab=integration"]}>
        <Routes>
          <Route path="/command-center" element={<CommandCenterPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Command Center — Integration Gateway (B5)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    Object.values(mockInt).forEach((f) => f.mockReset());
    mockInt.configs.mockResolvedValue(CONFIGS);
    mockInt.logs.mockResolvedValue(LOGS);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("hides the tab and blocks the panel without integration.read", async () => {
    renderCC([]);
    expect(screen.queryByRole("button", { name: "Integration Gateway" })).not.toBeInTheDocument();
    expect(await screen.findByText(/needs one of:/i)).toBeInTheDocument();
    expect(mockInt.configs).not.toHaveBeenCalled();
  });

  it("shows configs + logs read-only for integration.read alone", async () => {
    renderCC(["integration.read"]);
    // 3 enabled systems -> 3 "Kill" buttons, all disabled without write
    const kills = await screen.findAllByRole("button", { name: "Kill" });
    expect(kills).toHaveLength(3);
    kills.forEach((b) => expect(b).toBeDisabled());
    expect(screen.getByRole("button", { name: "Re-enable" })).toBeDisabled();
    // logs table shows the 409
    expect(screen.getByText("409")).toBeInTheDocument();
  });

  it("flips the kill switch via PATCH when the caller holds integration.write", async () => {
    mockInt.setEnabled.mockResolvedValue({ id: 1, system_name: "CAD", enabled: false });
    renderCC(["integration.read", "integration.write"]);
    const kills = await screen.findAllByRole("button", { name: "Kill" });
    await userEvent.setup().click(kills[0]); // CAD, first in config order
    expect(mockInt.setEnabled).toHaveBeenCalledWith(1, false);
    expect(await screen.findByText(/kill switch ON — adapter calls now 409/i)).toBeInTheDocument();
  });

  it("surfaces a 403 from integration-gateway", async () => {
    mockInt.configs.mockRejectedValue(new ApiError(403, "forbidden"));
    renderCC(["integration.read"]);
    expect(await screen.findByText(/can't view integration config/i)).toBeInTheDocument();
  });
});
