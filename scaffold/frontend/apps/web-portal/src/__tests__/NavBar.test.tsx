import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { NavBar } from "../components/NavBar";
import { setToken } from "../lib/auth";
import { fakeJwt } from "../test/jwt";

function renderWith(permissions: string[]) {
  setToken(fakeJwt({ permissions, badge_number: "NAV-1" }));
  return render(
    <MemoryRouter>
      <NavBar />
    </MemoryRouter>,
  );
}

beforeEach(() => localStorage.clear());

describe("NavBar RBAC gating", () => {
  it("shows no domain links for a permissionless token", () => {
    renderWith([]);
    expect(screen.queryByRole("link", { name: "Officers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Training" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Community" })).not.toBeInTheDocument();
    // sign out is always available
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("shows Officers + approvals for an HR Officer, not Training/Community", () => {
    renderWith(["hr.officer.read", "hr.transfer.approve", "hr.leave.approve"]);
    expect(screen.getByRole("link", { name: "Officers" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Transfer approvals" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Leave approvals" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Training" })).not.toBeInTheDocument();
  });

  it("shows only approvals (not Officers) for a Station Commander without hr.officer.read", () => {
    renderWith(["case.read", "dashboard.view", "hr.transfer.approve", "hr.leave.approve"]);
    expect(screen.queryByRole("link", { name: "Officers" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Transfer approvals" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cases" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("shows Training + Compliance for a Training Officer", () => {
    renderWith(["training.cert.read"]);
    expect(screen.getByRole("link", { name: "Training" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Compliance" })).toBeInTheDocument();
  });
});
