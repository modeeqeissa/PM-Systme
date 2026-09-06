import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConcernDetailPage } from "../../pages/community/ConcernDetailPage";
import { ApiError, type Concern, type FollowUpAction } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const getConcern = vi.fn();
const setConcernStatus = vi.fn();
const forConcern = vi.fn();
const createFollowUp = vi.fn();
const setFollowUpStatus = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    community: {
      ...actual.community,
      concerns: { get: (...a: unknown[]) => getConcern(...a), setStatus: (...a: unknown[]) => setConcernStatus(...a) },
      followUps: {
        forConcern: (...a: unknown[]) => forConcern(...a),
        create: (...a: unknown[]) => createFollowUp(...a),
        setStatus: (...a: unknown[]) => setFollowUpStatus(...a),
      },
    },
  };
});

const concern = (over: Partial<Concern> = {}): Concern => ({
  id: "c-1",
  meeting_id: null,
  category: "traffic",
  description: "Speeding on Elm St",
  raised_by: null,
  status: "open",
  ...over,
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
      <MemoryRouter initialEntries={["/community/concerns/c-1"]}>
        <Routes>
          <Route path="/community/concerns/:concernId" element={<ConcernDetailPage />} />
          <Route path="/community/concerns" element={<div>concerns list</div>} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  [getConcern, setConcernStatus, forConcern, createFollowUp, setFollowUpStatus].forEach((m) => m.mockReset());
  getConcern.mockResolvedValue(concern());
  forConcern.mockResolvedValue([]);
});

describe("ConcernDetailPage", () => {
  it("renders the concern and its follow-up actions", async () => {
    forConcern.mockResolvedValue([fu(), fu({ id: "fu-2", status: "overdue", description: "Chase council" })]);
    renderPage(["community.read"]);
    expect(await screen.findByRole("heading", { name: "traffic" })).toBeInTheDocument();
    expect(screen.getByText("Arrange speed survey")).toBeInTheDocument();
    expect(screen.getByText("Chase council")).toBeInTheDocument();
    expect(screen.getByText("overdue")).toBeInTheDocument();
  });

  it("assigns a follow-up action with description/assigned_to/due_date", async () => {
    createFollowUp.mockResolvedValue(fu({ id: "fu-9" }));
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByRole("heading", { name: "traffic" });
    await user.click(screen.getByRole("button", { name: "Assign action" }));
    await user.type(screen.getByLabelText("Description"), "Arrange speed survey");
    await user.type(screen.getByLabelText("Assigned to (officer id)"), "0ffffff0-0000-0000-0000-000000000000");
    await user.type(screen.getByLabelText("Due date"), "2026-05-01");
    await user.click(screen.getByRole("button", { name: "Assign action" }));
    expect(createFollowUp).toHaveBeenCalledWith("c-1", {
      description: "Arrange speed survey",
      assigned_to: "0ffffff0-0000-0000-0000-000000000000",
      due_date: "2026-05-01",
    });
    expect(await screen.findByText("Follow-up action assigned.")).toBeInTheDocument();
  });

  it("marks a follow-up action completed", async () => {
    forConcern.mockResolvedValue([fu()]);
    setFollowUpStatus.mockResolvedValue(fu({ status: "completed" }));
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByText("Arrange speed survey");
    await user.click(screen.getByRole("button", { name: "mark completed" }));
    expect(setFollowUpStatus).toHaveBeenCalledWith("fu-1", "completed");
  });

  it("changes the concern status", async () => {
    setConcernStatus.mockResolvedValue(concern({ status: "resolved" }));
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByRole("heading", { name: "traffic" });
    await user.click(screen.getByRole("button", { name: "resolved" }));
    expect(setConcernStatus).toHaveBeenCalledWith("c-1", "resolved");
  });

  it("hides all write controls without community.write", async () => {
    forConcern.mockResolvedValue([fu()]);
    renderPage(["community.read"]);
    await screen.findByRole("heading", { name: "traffic" });
    expect(screen.queryByRole("button", { name: "Assign action" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "mark completed" })).not.toBeInTheDocument();
    expect(screen.queryByText("Set status:")).not.toBeInTheDocument();
  });

  it("shows a 404 for an unknown concern", async () => {
    getConcern.mockRejectedValue(new ApiError(404, "No concern with that id"));
    renderPage(["community.read"]);
    expect(await screen.findByText(/no concern with that id/i)).toBeInTheDocument();
  });
});
