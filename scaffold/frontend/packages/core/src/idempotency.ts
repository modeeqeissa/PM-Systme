import { useRef } from "react";

/**
 * A stable idempotency key for one logical write.
 *
 * Field-originated writes (FR-CASE-10) must carry an Idempotency-Key so the
 * server can dedupe retries. The contract that matters:
 *   - the key is generated ONCE per submission intent, client-side;
 *   - every retry of that submission (network failure, validation fix, a second
 *     click) reuses the SAME key;
 *   - only once the write has actually succeeded do we mint a new key for the
 *     next, separate write.
 *
 * The web-portal keeps the key for the lifetime of the form (useIdempotencyKey).
 * The offline field PWA persists it with the queued incident in IndexedDB, so a
 * sync that happens minutes later — possibly after several failed attempts —
 * still replays the write under the original key.
 */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

export interface IdempotencyKeyHandle {
  /** The current key — pass this to the API on every attempt. */
  current(): string;
  /** Start a fresh submission: mint and return a new key. */
  rotate(): string;
}

export function useIdempotencyKey(): IdempotencyKeyHandle {
  const ref = useRef<string>(newIdempotencyKey());
  return {
    current: () => ref.current,
    rotate: () => {
      ref.current = newIdempotencyKey();
      return ref.current;
    },
  };
}
