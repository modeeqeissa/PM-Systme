import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MeetingsPage } from "../../pages/community/MeetingsPage";
import { ApiError, type Meeting } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const listMeetings = vi.fn();
const createMeeting = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    community: {
      ...actual.community,
      meetings: { list: (...a: unknown[]) => listMeetings(...a), create: (...a: unknown[]) => createMeeting(...a) },
    },
  };
});

const meeting = (over: Partial<Meeting> = {}): Meeting => ({
  id: "m-1",
  station_id: "5ta7104e-0000-0000-0000-000000000000",
  facilitator_id: "fac00000-0000-0000-0000-000000000000",
  meeting_date: "2026-03-10",
  location: "Community Hall",
  attendee_summary: "~30 residents, 2 councillors",
  ...over,
});

function renderPage(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "CLO-1", station_id: "5ta7104e-0000-0000-0000-000000000000", sub: "fac00000-0000-0000-0000-000000000000" }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/community/meetings"]}>
        <Routes>
          <Route path="/community/meetings" element={<MeetingsPage />} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listMeetings.mockReset();
  createMeeting.mockReset();
  listMeetings.mockResolvedValue([]);
});

describe("MeetingsPage", () => {
  it("lists meetings with the attendee summary", async () => {
    listMeetings.mockResolvedValue([meeting()]);
    renderPage(["community.read"]);
    expect(await screen.findByText("Community Hall")).toBeInTheDocument();
    expect(screen.getByText("~30 residents, 2 councillors")).toBeInTheDocument();
  });

  it("hides the log form without community.write", async () => {
    renderPage(["community.read"]);
    await screen.findByText(/No meetings logged/i);
    expect(screen.queryByRole("button", { name: "Log meeting" })).not.toBeInTheDocument();
  });

  it("logs a meeting including attendee_summary, defaulting station/facilitator from the token", async () => {
    createMeeting.mockResolvedValue(meeting({ id: "m-2" }));
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByText(/No meetings logged/i);
    await user.click(screen.getByRole("button", { name: "Log meeting" }));
    await user.type(screen.getByLabelText("Meeting date"), "2026-04-01");
    await user.type(screen.getByLabelText("Location"), "Library");
    await user.type(screen.getByLabelText("Attendee summary"), "12 residents");
    listMeetings.mockResolvedValue([meeting({ id: "m-2", location: "Library", attendee_summary: "12 residents" })]);
    await user.click(screen.getByRole("button", { name: "Log meeting" }));

    expect(createMeeting).toHaveBeenCalledWith({
      station_id: "5ta7104e-0000-0000-0000-000000000000",
      facilitator_id: "fac00000-0000-0000-0000-000000000000",
      meeting_date: "2026-04-01",
      location: "Library",
      attendee_summary: "12 residents",
    });
    expect(await screen.findByText("Meeting logged.")).toBeInTheDocument();
  });

  it("surfaces a 403 on the list", async () => {
    listMeetings.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
    renderPage(["community.read"]);
    expect(await screen.findByText(/can't view meetings/i)).toBeInTheDocument();
  });
});
