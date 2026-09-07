/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// Field PWA — offline-first patrol app (a different architecture from
// web-portal). Local dev proxies same-origin /api/* paths to iam (auth),
// case (cases + incidents + statements + arrests) and evidence (logging).
const IAM = process.env.PMP_IAM_URL ?? "http://localhost:8001";
const CASE = process.env.PMP_CASE_URL ?? "http://localhost:8002";
const EVIDENCE = process.env.PMP_EVIDENCE_URL ?? "http://localhost:8003";
const PORT = Number(process.env.PMP_FIELD_PORT ?? 5190);

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      // Precache the app shell only. Offline data (the case list) and offline
      // writes (queued incidents) are handled explicitly in IndexedDB by the
      // app — NOT by the service worker caching API responses, which would
      // hide staleness and can't do write-queueing.
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg}"],
        navigateFallback: "index.html",
        navigateFallbackDenylist: [/^\/api\//],
      },
      manifest: {
        name: "PMP Field",
        short_name: "PMP Field",
        description: "Police Management Platform — field app for patrol officers",
        theme_color: "#0f172a",
        background_color: "#f8fafc",
        display: "standalone",
        start_url: "/",
        icons: [
          {
            src: "icon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any maskable",
          },
        ],
      },
    }),
  ],
  server: {
    port: PORT,
    strictPort: true,
    proxy: {
      "/api/iam": { target: IAM, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/iam/, "") },
      "/api/case": { target: CASE, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/case/, "") },
      "/api/evidence": { target: EVIDENCE, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/evidence/, "") },
    },
  },
  preview: {
    port: PORT,
    strictPort: true,
    proxy: {
      "/api/iam": { target: IAM, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/iam/, "") },
      "/api/case": { target: CASE, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/case/, "") },
      "/api/evidence": { target: EVIDENCE, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/evidence/, "") },
    },
  },
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost/" } },
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
