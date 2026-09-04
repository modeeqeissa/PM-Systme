import { describe, expect, it } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { newIdempotencyKey, useIdempotencyKey } from "../lib/idempotency";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

describe("idempotency key", () => {
  it("newIdempotencyKey returns a fresh v4 UUID each call", () => {
    const a = newIdempotencyKey();
    const b = newIdempotencyKey();
    expect(a).toMatch(UUID);
    expect(b).toMatch(UUID);
    expect(a).not.toBe(b);
  });

  it("useIdempotencyKey holds one key stable across renders, rotates only on request", () => {
    const { result, rerender } = renderHook(() => useIdempotencyKey());
    const first = result.current.current();
    expect(first).toMatch(UUID);

    rerender();
    expect(result.current.current()).toBe(first); // stable across re-render

    let rotated = "";
    act(() => {
      rotated = result.current.rotate();
    });
    expect(rotated).not.toBe(first);
    expect(result.current.current()).toBe(rotated);
  });
});
