import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FollowUpsPage } from "../../pages/community/FollowUpsPage";
import { ApiError, type FollowUpAction } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const listFollowUps = vi.fn();
const recompute = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    community: {
      ...actual.community,
      followUps: { list: (...a: unknown[]) => listFollowUps(...a), recompute: (...a: unknown[]) => recompute(...a) },
    },
  };
});

const fu = (over: Partial<FollowUpAction> = {}): FollowUpAction => ({
  id: "fu-1",
  concern_id: "c-1",
  description: "Arrange speed survey",
  assigned_to: "0ffffff0-0000-0000-0000-000000000000",
  due_date: "2026-05-01",
  status: "pending",
  ...over,
});

function renderPage(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "CLO-1" }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/community/follow-ups"]}>
        <Routes>
          <Route path="/community/follow-ups" element={<FollowUpsPage />} />
          <Route path="/community/concerns/:concernId" element={<div>detail screen</div>} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listFollowUps.mockReset();
  recompute.mockReset();
  listFollowUps.mockResolvedValue([]);
});

describe("FollowUpsPage", () => {
  it("defaults to the pending bucket", async () => {
    renderPage(["community.read"]);
    await screen.findByText(/Nothing in this bucket/i);
    expect(listFollowUps).toHaveBeenCalledWith({ status: "pending" });
  });

  it("recomputes overdue, shows the result, and jumps to the overdue bucket", async () => {
    recompute.mockResolvedValue({ checked: 5, updated: 2 });
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByText(/Nothing in this bucket/i);
    listFollowUps.mockResolvedValue([fu({ status: "overdue" })]);
    await user.click(screen.getByRole("button", { name: "Recompute overdue" }));
    expect(recompute).toHaveBeenCalled();
    expect(await screen.findByText(/checked 5, newly overdue 2/i)).toBeInTheDocument();
    expect(listFollowUps).toHaveBeenLastCalledWith({ status: "overdue" });
    expect(await screen.findByText("Arrange speed survey")).toBeInTheDocument();
  });

  it("hides the recompute button without community.write", async () => {
    renderPage(["community.read"]);
    await screen.findByText(/Nothing in this bucket/i);
    expect(screen.queryByRole("button", { name: "Recompute overdue" })).not.toBeInTheDocument();
  });

  it("links each action to its concern", async () => {
    listFollowUps.mockResolvedValue([fu()]);
    renderPage(["community.read"]);
    expect(await screen.findByRole("link", { name: "Arrange speed survey" })).toHaveAttribute(
      "href",
      "/community/concerns/c-1",
    );
  });

  it("surfaces a 403 on the queue", async () => {
    listFollowUps.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
    renderPage(["community.read"]);
    expect(await screen.findByText(/can't view follow-up actions/i)).toBeInTheDocument();
  });
});
