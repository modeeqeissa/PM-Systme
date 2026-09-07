import "@testing-library/jest-dom/vitest";
import "fake-indexeddb/auto";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// In-memory Web Storage (jsdom's is not reliably wired under newer Node).
class MemStorage implements Storage {
  #m = new Map<string, string>();
  get length() {
    return this.#m.size;
  }
  clear() {
    this.#m.clear();
  }
  getItem(k: string) {
    return this.#m.has(k) ? this.#m.get(k)! : null;
  }
  setItem(k: string, v: string) {
    this.#m.set(k, String(v));
  }
  removeItem(k: string) {
    this.#m.delete(k);
  }
  key(i: number) {
    return [...this.#m.keys()][i] ?? null;
  }
}
Object.defineProperty(globalThis, "localStorage", {
  value: new MemStorage(),
  configurable: true,
  writable: true,
});

if (typeof globalThis.crypto?.randomUUID !== "function") {
  // deterministic-enough uuid v4 for tests
  Object.defineProperty(globalThis, "crypto", {
    value: {
      ...globalThis.crypto,
      randomUUID: () =>
        "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
          const r = (Math.random() * 16) | 0;
          return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
        }),
    },
    configurable: true,
  });
}

afterEach(() => {
  cleanup();
  localStorage.clear();
});
