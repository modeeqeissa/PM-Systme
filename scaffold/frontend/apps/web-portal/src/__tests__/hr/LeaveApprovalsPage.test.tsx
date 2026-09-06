import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LeaveApprovalsPage } from "../../pages/hr/LeaveApprovalsPage";
import { ApiError, type LeaveRequest } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const queue = vi.fn();
const decide = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    hr: { ...actual.hr, leave: { queue: (...a: unknown[]) => queue(...a), decide: (...a: unknown[]) => decide(...a) } },
  };
});

function leave(over: Partial<LeaveRequest> = {}): LeaveRequest {
  return {
    id: "l-1",
    officer_id: "0ffffff0-0000-0000-0000-000000000000",
    leave_type: "annual",
    start_date: "2026-10-01",
    end_date: "2026-10-05",
    status: "pending",
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
      <MemoryRouter initialEntries={["/hr/leave"]}>
        <Routes>
          <Route path="/hr/leave" element={<LeaveApprovalsPage />} />
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

describe("LeaveApprovalsPage", () => {
  it("loads the pending queue", async () => {
    queue.mockResolvedValue([leave()]);
    renderPage(["hr.leave.read", "hr.leave.approve"]);
    await screen.findByText(/annual/);
    expect(queue).toHaveBeenCalledWith("pending");
  });

  it("approves a pending leave request with approved_by", async () => {
    queue.mockResolvedValue([leave()]);
    decide.mockResolvedValue(leave({ status: "approved" }));
    const user = userEvent.setup();
    renderPage(["hr.leave.read", "hr.leave.approve"]);
    await screen.findByText(/annual/);
    await user.click(screen.getByRole("button", { name: "Review" }));
    await user.type(screen.getByLabelText("Approved by (officer id)"), "appr-9");
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(decide).toHaveBeenCalledWith("l-1", { status: "approved", approved_by: "appr-9" });
  });

  it("hides Review without hr.leave.approve", async () => {
    queue.mockResolvedValue([leave()]);
    renderPage(["hr.leave.read"]);
    await screen.findByText(/annual/);
    expect(screen.queryByRole("button", { name: "Review" })).not.toBeInTheDocument();
  });

  it("shows a 403 when the queue itself is forbidden", async () => {
    queue.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
    renderPage(["hr.leave.read"]);
    expect(await screen.findByText(/can't view the leave queue/i)).toBeInTheDocument();
  });
});
