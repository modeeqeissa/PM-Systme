import pmpPreset from "../../packages/ui/tailwind-preset.cjs";

/** @type {import('tailwindcss').Config} */
export default {
  presets: [pmpPreset],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
    // shared component library
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
  theme: { extend: {} },
  plugins: [],
};
