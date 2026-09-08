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
const changePassword = vi.fn();

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return {
    ...actual,
    iam: {
      login: (...a: unknown[]) => login(...a),
      verifyMfa: (...a: unknown[]) => verifyMfa(...a),
      enrollMfa: (...a: unknown[]) => enrollMfa(...a),
      changePassword: (...a: unknown[]) => changePassword(...a),
    },
  };
});

/** minimal JWT with a decodable `sub` payload */
function jwtWithSub(sub: string): string {
  const b64 = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `h.${b64({ sub, exp: Math.floor(Date.now() / 1000) + 900, iat: 0 })}.sig`;
}

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
  changePassword.mockReset();
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

  it("forces a password reset when the token comes back password_expired (FR-IAM-07)", async () => {
    const user = userEvent.setup();
    login.mockResolvedValue({ mfa_token: "mfa-x", mfa_enrolled: true, token_type: "bearer", expires_in: 300 });
    verifyMfa.mockResolvedValue({
      access_token: jwtWithSub("user-9"),
      refresh_token: "r",
      token_type: "bearer",
      expires_in: 900,
      password_expired: true,
    });
    changePassword.mockResolvedValue(204);

    renderLogin();
    await user.type(screen.getByLabelText("Badge number"), "OFF-9");
    await user.type(screen.getByLabelText("Password"), "Old!password123");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(await screen.findByLabelText(/6-digit authenticator code/i), "123456");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    // not signed in — forced-reset step instead
    expect(await screen.findByText(/your password has expired/i)).toBeInTheDocument();
    expect(getToken()).toBeNull();

    await user.type(screen.getByLabelText("New password"), "Br4nd!newpass456");
    await user.click(screen.getByRole("button", { name: "Update password" }));

    expect(changePassword).toHaveBeenCalledWith(
      "user-9",
      { current_password: "Old!password123", new_password: "Br4nd!newpass456" },
      jwtWithSub("user-9"),
    );
    // back on the credentials step with a success notice, still not signed in
    expect(await screen.findByText(/password updated/i)).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });

  it("shows the policy error if the forced-reset password is rejected", async () => {
    const user = userEvent.setup();
    login.mockResolvedValue({ mfa_token: "mfa-y", mfa_enrolled: true, token_type: "bearer", expires_in: 300 });
    verifyMfa.mockResolvedValue({
      access_token: jwtWithSub("user-7"),
      refresh_token: "r",
      token_type: "bearer",
      expires_in: 900,
      password_expired: true,
    });
    changePassword.mockRejectedValue(
      new ApiError(400, "Password policy: must not reuse any of the last 5 passwords"),
    );

    renderLogin();
    await user.type(screen.getByLabelText("Badge number"), "OFF-7");
    await user.type(screen.getByLabelText("Password"), "Old!password123");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await user.type(await screen.findByLabelText(/6-digit authenticator code/i), "123456");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    await user.type(await screen.findByLabelText("New password"), "Old!password123");
    await user.click(screen.getByRole("button", { name: "Update password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/must not reuse/i);
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
