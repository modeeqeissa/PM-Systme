/* Shared Tailwind theme for every PMP frontend. Consume via:
     presets: [require("@pmp/ui/tailwind-preset.cjs")]
   Colour values mirror packages/ui/src/theme.css (CSS vars) 1:1. */
/** @type {import('tailwindcss').Config} */
module.exports = {
  theme: {
    extend: {
      colors: {
        bg: "#0b0f19",
        surface: {
          DEFAULT: "#131824",
          2: "#1a2130",
          3: "#212a3b",
        },
        hair: {
          DEFAULT: "#262d3d", // hairline border
          soft: "#1e2431",
        },
        ink: {
          DEFAULT: "#e8ecf6",
          muted: "#9aa6c0",
          faint: "#667192",
        },
        accent: {
          command: "#3b82f6",
          hr: "#818cf8",
          dashboard: "#38bdf8",
          community: "#34d399",
          cases: "#e0a340",
          training: "#a78bfa",
        },
        ok: "#34d399",
        warn: "#fbbf24",
        bad: "#f87171",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      borderRadius: {
        xl: "12px",
      },
      backdropBlur: {
        panel: "10px",
      },
      keyframes: {
        "pmp-pulse": {
          "0%": { boxShadow: "0 0 0 0 var(--pmp-pulse-ring, rgba(52,211,153,.55))" },
          "70%": { boxShadow: "0 0 0 7px rgba(0,0,0,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(0,0,0,0)" },
        },
        "pmp-ticker": {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-50%)" },
        },
      },
      animation: {
        "pmp-pulse": "pmp-pulse 1.8s infinite",
        "pmp-ticker": "pmp-ticker 28s linear infinite",
      },
    },
  },
};
