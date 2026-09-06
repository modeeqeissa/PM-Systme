import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CompliancePage } from "../../pages/training/CompliancePage";
import { ApiError, type OfficerCertification } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const listOfficerCerts = vi.fn();
const recompute = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    training: {
      ...actual.training,
      officerCerts: { list: (...a: unknown[]) => listOfficerCerts(...a), recompute: (...a: unknown[]) => recompute(...a) },
    },
  };
});

const oc = (over: Partial<OfficerCertification> = {}): OfficerCertification => ({
  id: "oc-1",
  officer_id: "0ffffff0-0000-0000-0000-000000000000",
  certification_id: 10,
  issued_date: "2025-01-01",
  expires_date: "2026-01-01",
  status: "expired",
  ...over,
});

function renderPage(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "TR-1" }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/training/compliance"]}>
        <Routes>
          <Route path="/training/compliance" element={<CompliancePage />} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listOfficerCerts.mockReset();
  recompute.mockReset();
  listOfficerCerts.mockResolvedValue([]);
});

describe("CompliancePage", () => {
  it("defaults to the expiring_soon bucket", async () => {
    renderPage(["training.cert.read"]);
    await screen.findByText(/Nothing in this bucket/i);
    expect(listOfficerCerts).toHaveBeenCalledWith({ status: "expiring_soon" });
  });

  it("switches bucket to expired", async () => {
    const user = userEvent.setup();
    renderPage(["training.cert.read"]);
    await screen.findByText(/Nothing in this bucket/i);
    listOfficerCerts.mockResolvedValue([oc()]);
    await user.click(screen.getByRole("button", { name: "Expired" }));
    expect(listOfficerCerts).toHaveBeenLastCalledWith({ status: "expired" });
    expect(await screen.findByText("0ffffff0-0000-0000-0000-000000000000")).toBeInTheDocument();
  });

  it("runs recompute and shows the checked/updated result (write only)", async () => {
    recompute.mockResolvedValue({ checked: 7, updated: 2 });
    const user = userEvent.setup();
    renderPage(["training.cert.read", "training.cert.write"]);
    await screen.findByText(/Nothing in this bucket/i);
    await user.click(screen.getByRole("button", { name: "Recompute status" }));
    expect(recompute).toHaveBeenCalled();
    expect(await screen.findByText(/checked 7, updated 2/i)).toBeInTheDocument();
  });

  it("hides the recompute button without training.cert.write", async () => {
    renderPage(["training.cert.read"]);
    await screen.findByText(/Nothing in this bucket/i);
    expect(screen.queryByRole("button", { name: "Recompute status" })).not.toBeInTheDocument();
  });

  it("surfaces a 403 on the list", async () => {
    listOfficerCerts.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
    renderPage(["training.cert.read"]);
    expect(await screen.findByText(/can't view compliance/i)).toBeInTheDocument();
  });
});
