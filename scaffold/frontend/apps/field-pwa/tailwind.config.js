import pmpPreset from "../../packages/ui/tailwind-preset.cjs";

/** @type {import('tailwindcss').Config} */
export default {
  // Shares the PMP colour + font tokens so field-pwa can adopt them later.
  // This pass keeps the existing light, 44px-touch-target layout as-is.
  presets: [pmpPreset],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
  theme: { extend: {} },
  plugins: [],
};
