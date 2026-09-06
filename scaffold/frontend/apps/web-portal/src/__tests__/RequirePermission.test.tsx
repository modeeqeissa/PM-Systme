import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { RequirePermission } from "../routes/RequirePermission";
import { setToken } from "../lib/auth";
import { fakeJwt } from "../test/jwt";

function renderWith(permissions: string[]) {
  setToken(fakeJwt({ permissions }));
  return render(
    <MemoryRouter>
      <RequirePermission anyOf={["hr.discipline.read"]}>
        <div>secret discipline screen</div>
      </RequirePermission>
    </MemoryRouter>,
  );
}

beforeEach(() => localStorage.clear());

describe("RequirePermission", () => {
  it("renders children when the caller holds one of the permissions", () => {
    renderWith(["hr.discipline.read"]);
    expect(screen.getByText("secret discipline screen")).toBeInTheDocument();
  });

  it("blocks with a not-authorised card when the caller holds none", () => {
    renderWith(["hr.officer.read"]);
    expect(screen.queryByText("secret discipline screen")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/doesn't have access/i);
    expect(screen.getByText("hr.discipline.read")).toBeInTheDocument();
  });
});
