/// <reference types="vitest/config" />
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local dev has no API gateway, and the services run on separate ports with no
// CORS. Proxy same-origin paths to each service so the browser sees one origin.
// In staging/prod the API gateway (SRS §3.5) routes by path prefix instead.
const IAM = process.env.PMP_IAM_URL ?? "http://localhost:8001";
const CASE = process.env.PMP_CASE_URL ?? "http://localhost:8002";
// 5173 (Vite's default) is often taken; override with PMP_PORT if 5180 clashes too.
const PORT = Number(process.env.PMP_PORT ?? 5180);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@pmp/ui": fileURLToPath(new URL("../../packages/ui/src", import.meta.url)),
    },
  },
  server: {
    port: PORT,
    strictPort: true,
    proxy: {
      // Prefixes under /api/* so they can't collide with client routes (/cases, ...).
      "/api/iam": { target: IAM, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/iam/, "") },
      "/api/case": { target: CASE, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/case/, "") },
    },
  },
  test: {
    environment: "jsdom",
    // jsdom's default about:blank is an opaque origin -> localStorage throws
    environmentOptions: { jsdom: { url: "http://localhost/" } },
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
