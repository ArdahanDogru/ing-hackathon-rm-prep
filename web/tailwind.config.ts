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
    },
  },
  plugins: [],
} satisfies Config;
