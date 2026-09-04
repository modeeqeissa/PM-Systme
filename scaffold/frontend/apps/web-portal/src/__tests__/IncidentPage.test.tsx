import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { IncidentPage } from "../pages/IncidentPage";
import { ApiError, type Incident } from "../lib/api";
import { setToken } from "../lib/auth";
import { fakeJwt } from "../test/jwt";

const createIncident = vi.fn();
const createCase = vi.fn();

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    incidents: { create: (...a: unknown[]) => createIncident(...a) },
    cases: { create: (...a: unknown[]) => createCase(...a) },
  };
});

const SUB = "11111111-1111-4111-8111-111111111111";
const STATION = "22222222-2222-4222-8222-222222222222";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function incident(over: Partial<Incident> = {}): Incident {
  return {
    id: "99999999-9999-4999-8999-999999999999",
    reported_by: SUB,
    incident_type: "burglary",
    description: "forced rear door",
    station_id: STATION,
    reported_at: "2026-09-05T09:00:00.000Z",
    created_at: "2026-09-05T09:00:01.000Z",
    latitude: null,
    longitude: null,
    ...over,
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/incidents/new"]}>
      <Routes>
        <Route path="/incidents/new" element={<IncidentPage />} />
        <Route path="/cases" element={<div>cases screen</div>} />
        <Route path="/login" element={<div>login screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Incident type"), "burglary");
  await user.type(screen.getByLabelText("Description"), "forced rear door");
  // station id is pre-filled from the token; leave it
}

beforeEach(() => {
  createIncident.mockReset();
  createCase.mockReset();
  setToken(fakeJwt({ sub: SUB, badge_number: "OFF-7", station_id: STATION }));
});

describe("IncidentPage — file an incident (FR-CASE-01)", () => {
  it("submits with reported_by/station from the token and a UUID Idempotency-Key", async () => {
    const user = userEvent.setup();
    createIncident.mockResolvedValue({ incident: incident(), replayed: false });

    renderPage();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "File incident" }));

    await screen.findByText("Incident filed.");
    expect(createIncident).toHaveBeenCalledTimes(1);
    const [body, key] = createIncident.mock.calls[0];
    expect(body).toMatchObject({
      reported_by: SUB,
      station_id: STATION,
      incident_type: "burglary",
      description: "forced rear door",
    });
    expect(typeof body.reported_at).toBe("string");
    expect(key).toMatch(UUID);
  });

  it("REUSES the same Idempotency-Key when retrying after a network failure", async () => {
    const user = userEvent.setup();
    createIncident
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({ incident: incident(), replayed: false });

    renderPage();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "File incident" }));

    // network error surfaced, entry not lost
    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn't reach case-service/i);

    // retry — same button, same submission
    await user.click(screen.getByRole("button", { name: "File incident" }));
    await screen.findByText("Incident filed.");

    expect(createIncident).toHaveBeenCalledTimes(2);
    expect(createIncident.mock.calls[0][1]).toBe(createIncident.mock.calls[1][1]);
  });

  it("REUSES the key when fixing a 422 and resubmitting", async () => {
    const user = userEvent.setup();
    createIncident
      .mockRejectedValueOnce(
        new ApiError(422, "Unprocessable Entity", {
          detail: [{ loc: ["body", "description"], msg: "field required", type: "missing" }],
        }),
      )
      .mockResolvedValueOnce({ incident: incident(), replayed: false });

    renderPage();
    await user.type(screen.getByLabelText("Incident type"), "burglary");
    await user.type(screen.getByLabelText("Description"), "x");
    await user.click(screen.getByRole("button", { name: "File incident" }));

    expect(await screen.findByText("field required")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Description"), " forced rear door");
    await user.click(screen.getByRole("button", { name: "File incident" }));
    await screen.findByText("Incident filed.");

    expect(createIncident).toHaveBeenCalledTimes(2);
    expect(createIncident.mock.calls[0][1]).toBe(createIncident.mock.calls[1][1]);
  });

  it('mints a NEW key for the next incident after "File another"', async () => {
    const user = userEvent.setup();
    createIncident.mockResolvedValue({ incident: incident(), replayed: false });

    renderPage();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "File incident" }));
    await screen.findByText("Incident filed.");

    await user.click(screen.getByRole("button", { name: "File another incident" }));
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "File incident" }));
    await screen.findByText("Incident filed.");

    expect(createIncident).toHaveBeenCalledTimes(2);
    expect(createIncident.mock.calls[0][1]).not.toBe(createIncident.mock.calls[1][1]);
  });

  it("treats a duplicate submit (200 replay) as success, not an error", async () => {
    const user = userEvent.setup();
    createIncident.mockResolvedValue({ incident: incident(), replayed: true });

    renderPage();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "File incident" }));

    expect(await screen.findByText(/already filed with that idempotency key/i)).toBeInTheDocument();
    expect(screen.getByText("burglary")).toBeInTheDocument(); // the original record is shown
  });

  it("surfaces a 403 with a clear permission message", async () => {
    const user = userEvent.setup();
    createIncident.mockRejectedValue(new ApiError(403, "RBAC scope denied"));

    renderPage();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "File incident" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/can't file incidents/i);
    expect(screen.getByText(/case\.write/)).toBeInTheDocument();
  });

  it("escalates a filed incident into a case and goes to the case list", async () => {
    const user = userEvent.setup();
    const inc = incident();
    createIncident.mockResolvedValue({ incident: inc, replayed: false });
    createCase.mockResolvedValue({ id: "c1" });

    renderPage();
    await fillForm(user);
    await user.click(screen.getByRole("button", { name: "File incident" }));
    await screen.findByText("Incident filed.");

    await user.click(screen.getByRole("button", { name: "Escalate to a case" }));
    await screen.findByText("cases screen");

    expect(createCase).toHaveBeenCalledWith({
      incident_id: inc.id,
      lead_officer_id: SUB,
    });
  });
});
