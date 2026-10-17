import type { Config } from "tailwindcss";
import { colors } from "./src/theme";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "Segoe UI", "Arial", "sans-serif"] },
      colors: {
        brand: colors.brand,
        ink: colors.ink,
        muted: colors.muted,
        surface: colors.surface,
        cobalt: colors.chart,
        catgrey: colors.category,
      },
      // W41: the steps of the meeting-text wait come in one by one
      keyframes: { rise: { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } } },
      animation: { rise: "rise 0.35s ease-out both" },
    },
  },
  plugins: [],
} satisfies Config;
