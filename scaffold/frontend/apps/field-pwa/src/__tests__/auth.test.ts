import { beforeEach, describe, expect, it } from "vitest";
import {
  accessTokenUsable,
  clearTokens,
  decodeJwt,
  hasSession,
  isExpired,
  setTokens,
} from "../lib/auth";

function jwt(claims: Record<string, unknown>): string {
  const enc = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const now = Math.floor(Date.now() / 1000);
  return [
    enc({ alg: "RS256", typ: "JWT" }),
    enc({ sub: "u-1", badge_number: "B-1", station_id: "s-1", roles: [], permissions: [], iat: now, exp: now + 900, ...claims }),
    "sig",
  ].join(".");
}

beforeEach(() => {
  clearTokens();
});

describe("field auth", () => {
  it("decodes an access JWT and detects expiry", () => {
    const good = jwt({});
    expect(decodeJwt<{ sub: string }>(good)?.sub).toBe("u-1");
    expect(isExpired(decodeJwt(good))).toBe(false);

    const stale = jwt({ exp: Math.floor(Date.now() / 1000) - 60 });
    expect(isExpired(decodeJwt(stale))).toBe(true);
  });

  it("hasSession is true while the refresh window holds, even with a stale access token", () => {
    setTokens(jwt({ exp: Math.floor(Date.now() / 1000) - 60 }), "opaque-refresh-abc");
    expect(accessTokenUsable()).toBe(false); // access token expired
    expect(hasSession()).toBe(true); // ...but the session (refresh window) still stands
  });

  it("hasSession is false with no refresh token", () => {
    expect(hasSession()).toBe(false);
  });

  it("hasSession expires once the 7-day window elapses", () => {
    setTokens(jwt({}), "opaque-refresh-abc");
    // rewind the obtained-at marker past the window
    localStorage.setItem(
      "pmp.field.tokens_obtained_at",
      String(Date.now() - 8 * 24 * 3600 * 1000),
    );
    expect(hasSession()).toBe(false);
  });
});
