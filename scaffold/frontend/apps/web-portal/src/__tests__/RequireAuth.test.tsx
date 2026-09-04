import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { RequireAuth } from "../routes/RequireAuth";
import { setToken } from "../lib/auth";
import { fakeJwt } from "../test/jwt";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>login screen</div>} />
        <Route
          path="/cases"
          element={
            <RequireAuth>
              <div>protected cases</div>
            </RequireAuth>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RequireAuth", () => {
  it("redirects to /login when there is no token", () => {
    renderAt("/cases");
    expect(screen.getByText("login screen")).toBeInTheDocument();
    expect(screen.queryByText("protected cases")).not.toBeInTheDocument();
  });

  it("redirects to /login when the token is expired", () => {
    setToken(fakeJwt({ exp: Math.floor(Date.now() / 1000) - 30 }));
    renderAt("/cases");
    expect(screen.getByText("login screen")).toBeInTheDocument();
  });

  it("renders the protected content with a valid token", () => {
    setToken(fakeJwt({}));
    renderAt("/cases");
    expect(screen.getByText("protected cases")).toBeInTheDocument();
  });
});
