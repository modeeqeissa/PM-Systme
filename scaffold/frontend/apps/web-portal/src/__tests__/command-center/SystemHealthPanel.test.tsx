import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { CommandCenterPage } from "../../pages/command-center/CommandCenterPage";
import { setToken } from "../../lib/auth";
import { fakeJwt } from "../../test/jwt";

/** A fetch stub that answers /health per proxy prefix. */
function healthFetch(map: Record<string, number | "network">) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const hit = Object.entries(map).find(([prefix]) => url.startsWith(prefix));
    const outcome = hit ? hit[1] : 404;
    if (outcome === "network") throw new TypeError("Failed to fetch");
    return new Response(
      outcome === 200 ? JSON.stringify({ status: "ok", service: "x" }) : "err",
      { status: outcome as number, headers: { "Content-Type": "application/json" } },
    );
  });
}

function renderCC() {
  setToken(fakeJwt({ permissions: [], badge_number: "OFF-1" }));
  return render(
    <MemoryRouter initialEntries={["/command-center"]}>
      <Routes>
        <Route path="/command-center" element={<CommandCenterPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Command Center — System Health (B1)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", healthFetch({ "/api/": 200 }));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("is reachable with only an auth token — no permission gate", async () => {
    renderCC();
    expect(await screen.findByRole("heading", { name: "Command Center" })).toBeInTheDocument();
    expect(screen.getByText("System Health")).toBeInTheDocument();
  });

  it("polls every service's /health and shows each as up", async () => {
    renderCC();
    // all 10 services rendered by name
    for (const name of [
      "iam-service",
      "case-service",
      "evidence-service",
      "community-service",
      "training-service",
      "hr-service",
      "dashboard-service",
      "notification-service",
      "audit-service",
      "integration-gateway-service",
    ]) {
      expect(await screen.findByText(name)).toBeInTheDocument();
    }
    expect(await screen.findByText("all 10 services up")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/iam\/health$/),
      expect.anything(),
    );
  });

  it("marks a service down when its /health is unreachable", async () => {
    vi.stubGlobal("fetch", healthFetch({ "/api/case/": "network", "/api/": 200 }));
    renderCC();
    expect(await screen.findByText("1 service down")).toBeInTheDocument();
    expect(await screen.findByText("unreachable")).toBeInTheDocument();
  });

  it("marks a service down on a non-200 /health", async () => {
    vi.stubGlobal("fetch", healthFetch({ "/api/dash/": 503, "/api/": 200 }));
    renderCC();
    expect(await screen.findByText("1 service down")).toBeInTheDocument();
    expect(await screen.findByText("HTTP 503")).toBeInTheDocument();
  });
});
