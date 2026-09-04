import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Node 26 ships an experimental global `localStorage` that needs
// --localstorage-file; jsdom's isn't reliably wired under it. Give the tests a
// plain in-memory implementation of the Web Storage interface.
class MemStorage implements Storage {
  #m = new Map<string, string>();
  get length() {
    return this.#m.size;
  }
  clear() {
    this.#m.clear();
  }
  getItem(key: string) {
    return this.#m.has(key) ? this.#m.get(key)! : null;
  }
  setItem(key: string, value: string) {
    this.#m.set(key, String(value));
  }
  removeItem(key: string) {
    this.#m.delete(key);
  }
  key(index: number) {
    return [...this.#m.keys()][index] ?? null;
  }
}

Object.defineProperty(globalThis, "localStorage", {
  value: new MemStorage(),
  configurable: true,
  writable: true,
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});
