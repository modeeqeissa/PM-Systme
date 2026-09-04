/** Build an unsigned JWT-shaped string for tests (the browser never verifies it). */
export function fakeJwt(claims: Record<string, unknown>): string {
  const enc = (o: unknown) =>
    btoa(JSON.stringify(o)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const now = Math.floor(Date.now() / 1000);
  return [
    enc({ alg: "RS256", typ: "JWT" }),
    enc({ iat: now, exp: now + 900, sub: "u-1", badge_number: "B-1", roles: [], permissions: [], station_id: "s-1", ...claims }),
    "sig",
  ].join(".");
}
