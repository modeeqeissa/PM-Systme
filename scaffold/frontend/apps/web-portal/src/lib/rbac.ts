/**
 * Client-side RBAC helpers.
 *
 * The API is the real authority (it 403s a token without the permission); these
 * helpers only decide what to *show* — nav items, whole routes, action buttons —
 * so a user never sees a control that would just 403. Permission codes match
 * identity_db's `permissions.code` values (CLAUDE.md rule 4).
 */
import { currentClaims } from "./auth";

export function permissions(): string[] {
  return currentClaims()?.permissions ?? [];
}

export function hasPerm(code: string): boolean {
  return permissions().includes(code);
}

export function hasAnyPerm(codes: string[]): boolean {
  const held = permissions();
  return codes.some((c) => held.includes(c));
}
