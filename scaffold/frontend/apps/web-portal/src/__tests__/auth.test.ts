import { describe, expect, it } from "vitest";
import {
  clearToken,
  decodeToken,
  getToken,
  hasValidToken,
  isExpired,
  setToken,
} from "../lib/auth";
import { fakeJwt } from "../test/jwt";

describe("auth token utils", () => {
  it("decodes the claims payload", () => {
    const t = fakeJwt({ sub: "abc", badge_number: "OFF-9", roles: ["Investigator"] });
    const claims = decodeToken(t);
    expect(claims?.sub).toBe("abc");
    expect(claims?.badge_number).toBe("OFF-9");
    expect(claims?.roles).toEqual(["Investigator"]);
  });

  it("returns null for a malformed token", () => {
    expect(decodeToken("not-a-jwt")).toBeNull();
  });

  it("treats an expired token as expired (with skew)", () => {
    const past = Math.floor(Date.now() / 1000) - 60;
    expect(isExpired({ exp: past } as never)).toBe(true);
    const future = Math.floor(Date.now() / 1000) + 3600;
    expect(isExpired({ exp: future } as never)).toBe(false);
  });

  it("hasValidToken reflects storage + expiry", () => {
    expect(hasValidToken()).toBe(false);
    setToken(fakeJwt({}));
    expect(getToken()).not.toBeNull();
    expect(hasValidToken()).toBe(true);

    setToken(fakeJwt({ exp: Math.floor(Date.now() / 1000) - 10 }));
    expect(hasValidToken()).toBe(false);

    clearToken();
    expect(hasValidToken()).toBe(false);
  });
});
