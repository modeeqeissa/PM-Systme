import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConcernsPage } from "../../pages/community/ConcernsPage";
import { type Concern } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const listConcerns = vi.fn();
const createConcern = vi.fn();
const setStatus = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    community: {
      ...actual.community,
      concerns: {
        list: (...a: unknown[]) => listConcerns(...a),
        create: (...a: unknown[]) => createConcern(...a),
        setStatus: (...a: unknown[]) => setStatus(...a),
      },
    },
  };
});

const concern = (over: Partial<Concern> = {}): Concern => ({
  id: "c-1",
  meeting_id: null,
  category: "traffic",
  description: "Speeding on Elm St",
  raised_by: "A. Resident",
  status: "open",
  ...over,
});

function renderPage(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "CLO-1" }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/community/concerns"]}>
        <Routes>
          <Route path="/community/concerns" element={<ConcernsPage />} />
          <Route path="/community/concerns/:concernId" element={<div>detail screen</div>} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  [listConcerns, createConcern, setStatus].forEach((m) => m.mockReset());
  listConcerns.mockResolvedValue([]);
});

describe("ConcernsPage", () => {
  it("lists concerns and links to detail", async () => {
    listConcerns.mockResolvedValue([concern()]);
    renderPage(["community.read"]);
    expect(await screen.findByRole("link", { name: "traffic" })).toHaveAttribute("href", "/community/concerns/c-1");
    expect(screen.getByText("Speeding on Elm St")).toBeInTheDocument();
    expect(screen.getByText("raised by A. Resident")).toBeInTheDocument();
  });

  it("filters by status through the API", async () => {
    listConcerns.mockResolvedValue([concern()]);
    const user = userEvent.setup();
    renderPage(["community.read"]);
    await screen.findByRole("link", { name: "traffic" });
    await user.selectOptions(screen.getByLabelText("Status"), "resolved");
    expect(listConcerns.mock.calls.at(-1)![0]).toMatchObject({ status: "resolved" });
  });

  it("logs a concern with description + raised_by, meeting_id null when blank", async () => {
    createConcern.mockResolvedValue(concern({ id: "c-2" }));
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByText(/No concerns match/i);
    await user.click(screen.getByRole("button", { name: "Log concern" }));
    await user.type(screen.getByLabelText("Category"), "noise");
    await user.type(screen.getByLabelText("Description"), "Loud bar after midnight");
    await user.type(screen.getByLabelText("Raised by"), "J. Doe");
    listConcerns.mockResolvedValue([concern({ id: "c-2", category: "noise" })]);
    await user.click(screen.getByRole("button", { name: "Log concern" }));
    expect(createConcern).toHaveBeenCalledWith({
      meeting_id: null,
      category: "noise",
      description: "Loud bar after midnight",
      raised_by: "J. Doe",
    });
    expect(await screen.findByText("Concern logged.")).toBeInTheDocument();
  });

  it("changes a concern's status inline (write only)", async () => {
    listConcerns.mockResolvedValue([concern()]);
    setStatus.mockResolvedValue(concern({ status: "in_progress" }));
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByRole("link", { name: "traffic" });
    await user.click(screen.getByRole("button", { name: "in progress" }));
    expect(setStatus).toHaveBeenCalledWith("c-1", "in_progress");
  });

  it("hides status controls and the log form without community.write", async () => {
    listConcerns.mockResolvedValue([concern()]);
    renderPage(["community.read"]);
    await screen.findByRole("link", { name: "traffic" });
    expect(screen.queryByText("Set status:")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Log concern" })).not.toBeInTheDocument();
  });
});
