import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TransferApprovalsPage } from "../../pages/hr/TransferApprovalsPage";
import { ApiError, type Transfer } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const queue = vi.fn();
const decide = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    hr: { ...actual.hr, transfers: { queue: (...a: unknown[]) => queue(...a), decide: (...a: unknown[]) => decide(...a) } },
  };
});

function transfer(over: Partial<Transfer> = {}): Transfer {
  return {
    id: "t-1",
    officer_id: "0ffffff0-0000-0000-0000-000000000000",
    to_unit_id: "unit2222-0000-0000-0000-000000000000",
    from_unit_id: "unit1111-0000-0000-0000-000000000000",
    status: "pending",
    requested_at: "2026-09-01T09:00:00Z",
    effective_date: null,
    approved_by: null,
    created_at: "2026-09-01T09:00:00Z",
    ...over,
  };
}

function renderPage(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "CMD-2" }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/hr/transfers"]}>
        <Routes>
          <Route path="/hr/transfers" element={<TransferApprovalsPage />} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  queue.mockReset();
  decide.mockReset();
  queue.mockResolvedValue([]);
});

describe("TransferApprovalsPage", () => {
  it("loads the pending queue on open", async () => {
    queue.mockResolvedValue([transfer()]);
    renderPage(["hr.transfer.read", "hr.transfer.approve"]);
    await screen.findByText(/Officer/);
    expect(queue).toHaveBeenCalledWith("pending");
  });

  it("approves a pending transfer with approved_by + effective_date", async () => {
    queue.mockResolvedValue([transfer()]);
    decide.mockResolvedValue(transfer({ status: "approved" }));
    const user = userEvent.setup();
    renderPage(["hr.transfer.read", "hr.transfer.approve"]);
    await screen.findByText(/Officer/);
    await user.click(screen.getByRole("button", { name: "Review" }));
    await user.type(screen.getByLabelText("Approved by (officer id)"), "appr-1");
    await user.type(screen.getByLabelText("Effective date"), "2026-10-01");
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(decide).toHaveBeenCalledWith("t-1", {
      status: "approved",
      approved_by: "appr-1",
      effective_date: "2026-10-01",
    });
  });

  it("rejects a pending transfer", async () => {
    queue.mockResolvedValue([transfer()]);
    decide.mockResolvedValue(transfer({ status: "rejected" }));
    const user = userEvent.setup();
    renderPage(["hr.transfer.read", "hr.transfer.approve"]);
    await screen.findByText(/Officer/);
    await user.click(screen.getByRole("button", { name: "Review" }));
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(decide).toHaveBeenCalledWith("t-1", { status: "rejected", approved_by: undefined, effective_date: undefined });
  });

  it("hides the Review action without hr.transfer.approve", async () => {
    queue.mockResolvedValue([transfer()]);
    renderPage(["hr.transfer.read"]);
    await screen.findByText(/Officer/);
    expect(screen.queryByRole("button", { name: "Review" })).not.toBeInTheDocument();
  });

  it("surfaces a 409 (transfer not pending) from the decide call", async () => {
    queue.mockResolvedValue([transfer()]);
    decide.mockRejectedValue(new ApiError(409, "Transfer is not pending"));
    const user = userEvent.setup();
    renderPage(["hr.transfer.read", "hr.transfer.approve"]);
    await screen.findByText(/Officer/);
    await user.click(screen.getByRole("button", { name: "Review" }));
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(await screen.findByText(/not pending/i)).toBeInTheDocument();
  });

  it("switches to the approved tab", async () => {
    const user = userEvent.setup();
    renderPage(["hr.transfer.read", "hr.transfer.approve"]);
    await screen.findByText(/No pending transfers/i);
    await user.click(screen.getByRole("button", { name: "approved" }));
    expect(queue).toHaveBeenLastCalledWith("approved");
  });
});
