import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { LoginPage } from "../pages/LoginPage";
import { ApiError } from "../lib/api";
import { getToken } from "../lib/auth";

const login = vi.fn();
const verifyMfa = vi.fn();
const enrollMfa = vi.fn();

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    iam: {
      login: (...a: unknown[]) => login(...a),
      verifyMfa: (...a: unknown[]) => verifyMfa(...a),
      enrollMfa: (...a: unknown[]) => enrollMfa(...a),
    },
  };
});

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/cases" element={<div>cases screen</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  login.mockReset();
  verifyMfa.mockReset();
  enrollMfa.mockReset();
});

describe("LoginPage", () => {
  it("runs the enrolled login → MFA → token flow and stores the JWT", async () => {
    const user = userEvent.setup();
    login.mockResolvedValue({ mfa_token: "mfa-1", mfa_enrolled: true, token_type: "bearer", expires_in: 300 });
    verifyMfa.mockResolvedValue({
      access_token: "header.payload.sig",
      refresh_token: "r",
      token_type: "bearer",
      expires_in: 900,
    });

    renderLogin();
    await user.type(screen.getByLabelText("Badge number"), "OFF-1");
    await user.type(screen.getByLabelText("Password"), "hunter2!");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    // now on the TOTP step
    const codeField = await screen.findByLabelText(/6-digit authenticator code/i);
    await user.type(codeField, "123456");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await screen.findByText("cases screen");
    expect(login).toHaveBeenCalledWith("OFF-1", "hunter2!");
    expect(verifyMfa).toHaveBeenLastCalledWith("mfa-1", "123456");
    expect(getToken()).toBe("header.payload.sig");
  });

  it("shows a friendly error for wrong credentials", async () => {
    const user = userEvent.setup();
    login.mockRejectedValue(new ApiError(401, "Invalid credentials"));

    renderLogin();
    await user.type(screen.getByLabelText("Badge number"), "OFF-1");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/wrong badge number or password/i);
    expect(getToken()).toBeNull();
  });

  it("surfaces the account-locked state", async () => {
    const user = userEvent.setup();
    login.mockRejectedValue(new ApiError(423, "locked"));

    renderLogin();
    await user.type(screen.getByLabelText("Badge number"), "OFF-1");
    await user.type(screen.getByLabelText("Password"), "x");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/locked/i);
  });

  it("offers TOTP enrollment when the account has no authenticator", async () => {
    const user = userEvent.setup();
    login.mockResolvedValue({ mfa_token: "mfa-2", mfa_enrolled: false, token_type: "bearer", expires_in: 300 });
    enrollMfa.mockResolvedValue({ secret: "BASE32SECRET", otpauth_uri: "otpauth://totp/PMP:OFF-1" });

    renderLogin();
    await user.type(screen.getByLabelText("Badge number"), "OFF-1");
    await user.type(screen.getByLabelText("Password"), "hunter2!");
    await user.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("BASE32SECRET")).toBeInTheDocument();
    expect(enrollMfa).toHaveBeenCalledWith("mfa-2");
  });
});
