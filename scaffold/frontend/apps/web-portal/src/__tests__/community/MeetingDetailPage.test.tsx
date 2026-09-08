import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MeetingDetailPage } from "../../pages/community/MeetingDetailPage";
import { ApiError, type Decision, type Meeting, type MeetingMinutes } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const getMeeting = vi.fn();
const getMinutes = vi.fn();
const createMinutes = vi.fn();
const updateMinutes = vi.fn();
const forMeetingDecisions = vi.fn();
const createDecision = vi.fn();
const setDecisionStatus = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    community: {
      ...actual.community,
      meetings: { ...actual.community.meetings, get: (...a: unknown[]) => getMeeting(...a) },
      minutes: {
        get: (...a: unknown[]) => getMinutes(...a),
        create: (...a: unknown[]) => createMinutes(...a),
        update: (...a: unknown[]) => updateMinutes(...a),
      },
      decisions: {
        forMeeting: (...a: unknown[]) => forMeetingDecisions(...a),
        create: (...a: unknown[]) => createDecision(...a),
        setStatus: (...a: unknown[]) => setDecisionStatus(...a),
      },
    },
  };
});

const MID = "m-1";
const meeting = (o: Partial<Meeting> = {}): Meeting => ({
  id: MID, station_id: "s-1", community_id: "c-1", facilitator_id: "fac00000-0000-0000-0000-000000000000",
  meeting_date: "2026-03-10", location: "Community Hall", attendee_summary: "~30 residents", ...o,
});
const minutes = (o: Partial<MeetingMinutes> = {}): MeetingMinutes => ({
  id: "mm-1", meeting_id: MID, content: "Discussed potholes.", recorded_by: "u-1", ...o,
});
const decision = (o: Partial<Decision> = {}): Decision => ({
  id: "d-1", meeting_id: MID, description: "Petition the council.", status: "pending", ...o,
});

function renderPage(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "CLO-1", sub: "u-1" }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/community/meetings/${MID}`]}>
        <Routes>
          <Route path="/community/meetings/:meetingId" element={<MeetingDetailPage />} />
          <Route path="/community/meetings" element={<div>meetings list</div>} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  [getMeeting, getMinutes, createMinutes, updateMinutes, forMeetingDecisions, createDecision, setDecisionStatus].forEach(
    (m) => m.mockReset(),
  );
  getMeeting.mockResolvedValue(meeting());
  getMinutes.mockRejectedValue(new ApiError(404, "This meeting has no minutes yet"));
  forMeetingDecisions.mockResolvedValue([]);
});

describe("MeetingDetailPage", () => {
  it("shows the meeting header and empty states", async () => {
    renderPage(["community.read"]);
    expect(await screen.findByRole("heading", { name: "Community Hall" })).toBeInTheDocument();
    expect(await screen.findByText("No minutes recorded yet.")).toBeInTheDocument();
    expect(await screen.findByText("No decisions recorded yet.")).toBeInTheDocument();
  });

  it("records minutes when none exist, with recorded_by from the token", async () => {
    createMinutes.mockResolvedValue(minutes());
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByRole("heading", { name: "Community Hall" });

    await user.click(screen.getByRole("button", { name: "Record minutes" }));
    await user.type(screen.getByLabelText("Minutes content"), "Discussed potholes.");
    getMinutes.mockResolvedValue(minutes());
    await user.click(screen.getByRole("button", { name: "Save minutes" }));

    expect(createMinutes).toHaveBeenCalledWith(MID, {
      content: "Discussed potholes.",
      recorded_by: "u-1",
    });
  });

  it("edits existing minutes via PATCH", async () => {
    getMinutes.mockResolvedValue(minutes());
    updateMinutes.mockResolvedValue(minutes({ content: "Revised." }));
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByText("Discussed potholes.");

    await user.click(screen.getByRole("button", { name: "Edit minutes" }));
    const field = screen.getByLabelText("Minutes content");
    await user.clear(field);
    await user.type(field, "Revised.");
    await user.click(screen.getByRole("button", { name: "Save minutes" }));

    expect(updateMinutes).toHaveBeenCalledWith(MID, { content: "Revised." });
  });

  it("records a decision and moves it to implemented", async () => {
    createDecision.mockResolvedValue(decision());
    setDecisionStatus.mockResolvedValue(decision({ status: "implemented" }));
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByRole("heading", { name: "Community Hall" });

    await user.type(screen.getByLabelText("New decision"), "Petition the council.");
    forMeetingDecisions.mockResolvedValue([decision()]);
    await user.click(screen.getByRole("button", { name: "Record decision" }));
    expect(createDecision).toHaveBeenCalledWith(MID, { description: "Petition the council." });

    const item = (await screen.findByText("Petition the council.")).closest("li")!;
    await user.click(within(item).getByRole("button", { name: "Mark implemented" }));
    expect(setDecisionStatus).toHaveBeenCalledWith("d-1", "implemented");
  });

  it("hides write controls without community.write", async () => {
    getMinutes.mockResolvedValue(minutes());
    forMeetingDecisions.mockResolvedValue([decision()]);
    renderPage(["community.read"]);
    await screen.findByText("Discussed potholes.");
    expect(screen.queryByRole("button", { name: "Edit minutes" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark implemented" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("New decision")).not.toBeInTheDocument();
  });

  it("shows a 404 for an unknown meeting", async () => {
    getMeeting.mockRejectedValue(new ApiError(404, "No meeting with that id"));
    renderPage(["community.read"]);
    expect(await screen.findByText(/no meeting with that id/i)).toBeInTheDocument();
  });
});
