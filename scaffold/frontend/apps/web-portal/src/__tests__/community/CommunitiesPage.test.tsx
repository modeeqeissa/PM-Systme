import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CommunitiesPage } from "../../pages/community/CommunitiesPage";
import { ApiError, type Community, type Organization } from "../../lib/api";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

const listCommunities = vi.fn();
const createCommunity = vi.fn();
const updateCommunity = vi.fn();
const listOrganizations = vi.fn();
const createOrganization = vi.fn();

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    community: {
      ...actual.community,
      communities: {
        ...actual.community.communities,
        list: (...a: unknown[]) => listCommunities(...a),
        create: (...a: unknown[]) => createCommunity(...a),
        update: (...a: unknown[]) => updateCommunity(...a),
      },
      organizations: {
        ...actual.community.organizations,
        list: (...a: unknown[]) => listOrganizations(...a),
        create: (...a: unknown[]) => createOrganization(...a),
      },
    },
  };
});

const STATION = "5ta7104e-0000-0000-0000-000000000000";
const comm = (o: Partial<Community> = {}): Community => ({
  id: "c-1", name: "Riverside Watch", station_id: STATION, description: "East bank", ...o,
});
const org = (o: Partial<Organization> = {}): Organization => ({
  id: "o-1", name: "Ward Assoc", community_id: "c-1", contact_name: "Ada", contact_phone: "123", ...o,
});

function renderPage(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "CLO-1", station_id: STATION, sub: "u-1" }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/community/communities"]}>
        <Routes>
          <Route path="/community/communities" element={<CommunitiesPage />} />
          <Route path="/login" element={<div>login screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  [listCommunities, createCommunity, updateCommunity, listOrganizations, createOrganization].forEach((m) => m.mockReset());
  listCommunities.mockResolvedValue([]);
  listOrganizations.mockResolvedValue([]);
});

describe("CommunitiesPage", () => {
  it("lists communities and their organizations", async () => {
    listCommunities.mockResolvedValue([comm()]);
    listOrganizations.mockResolvedValue([org(), org({ id: "o-2", name: "Free NGO", community_id: null })]);
    renderPage(["community.read"]);

    expect(await screen.findByRole("heading", { name: "Riverside Watch" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Free NGO" })).toBeInTheDocument();
    // the standalone org's badge; the linked org's badge reads "Riverside Watch"
    expect(screen.getByText("unaffiliated")).toBeInTheDocument();
  });

  it("hides create forms without community.write", async () => {
    renderPage(["community.read"]);
    await screen.findByText("No communities yet.");
    expect(screen.queryByRole("button", { name: "New community" })).not.toBeInTheDocument();
  });

  it("creates a community with station defaulted from the token", async () => {
    createCommunity.mockResolvedValue(comm({ id: "c-2" }));
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByText("No communities yet.");

    await user.click(screen.getByRole("button", { name: "New community" }));
    await user.type(screen.getByLabelText("Name"), "Hilltop Forum");
    await user.click(screen.getByRole("button", { name: "Create community" }));

    expect(createCommunity).toHaveBeenCalledWith({
      name: "Hilltop Forum",
      station_id: STATION,
      description: null,
    });
    expect(await screen.findByText("Community created.")).toBeInTheDocument();
  });

  it("creates an organization linked to a chosen community", async () => {
    listCommunities.mockResolvedValue([comm()]);
    createOrganization.mockResolvedValue(org({ id: "o-9" }));
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByText("Riverside Watch");

    await user.click(screen.getByRole("button", { name: "New organization" }));
    await user.type(screen.getByLabelText("Name"), "Neighbourhood Trust");
    await user.selectOptions(screen.getByLabelText("Community (optional)"), "c-1");
    await user.click(screen.getByRole("button", { name: "Create organization" }));

    expect(createOrganization).toHaveBeenCalledWith({
      name: "Neighbourhood Trust",
      community_id: "c-1",
      contact_name: null,
      contact_phone: null,
    });
  });

  it("edits a community name (station stays)", async () => {
    listCommunities.mockResolvedValue([comm()]);
    updateCommunity.mockResolvedValue(comm({ name: "Riverside Neighbourhood Watch" }));
    const user = userEvent.setup();
    renderPage(["community.read", "community.write"]);
    await screen.findByText("Riverside Watch");

    await user.click(screen.getByRole("button", { name: "Edit" }));
    const nameField = screen.getByLabelText("Name");
    await user.clear(nameField);
    await user.type(nameField, "Riverside Neighbourhood Watch");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(updateCommunity).toHaveBeenCalledWith("c-1", {
      name: "Riverside Neighbourhood Watch",
      description: "East bank",
    });
  });

  it("surfaces a 403 on the communities list", async () => {
    listCommunities.mockRejectedValue(new ApiError(403, "RBAC scope denied"));
    renderPage(["community.read"]);
    expect(await screen.findByText(/can't view communities/i)).toBeInTheDocument();
  });
});
