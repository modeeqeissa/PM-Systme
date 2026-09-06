/// <reference types="vitest/config" />
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local dev has no API gateway, and the services run on separate ports with no
// CORS. Proxy same-origin paths to each service so the browser sees one origin.
// In staging/prod the API gateway (SRS §3.5) routes by path prefix instead.
const IAM = process.env.PMP_IAM_URL ?? "http://localhost:8001";
const CASE = process.env.PMP_CASE_URL ?? "http://localhost:8002";
const DASH = process.env.PMP_DASHBOARD_URL ?? "http://localhost:8007";
const EVIDENCE = process.env.PMP_EVIDENCE_URL ?? "http://localhost:8003";
const COMMUNITY = process.env.PMP_COMMUNITY_URL ?? "http://localhost:8004";
const TRAINING = process.env.PMP_TRAINING_URL ?? "http://localhost:8005";
const HR = process.env.PMP_HR_URL ?? "http://localhost:8006";
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
      "/api/dash": { target: DASH, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/dash/, "") },
      "/api/evidence": { target: EVIDENCE, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/evidence/, "") },
      "/api/community": { target: COMMUNITY, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/community/, "") },
      "/api/training": { target: TRAINING, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/training/, "") },
      "/api/hr": { target: HR, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/hr/, "") },
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
