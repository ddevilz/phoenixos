import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#0f1117",
        panel: "#1a1d27",
        border: "#2a2d3e",
        muted: "#6b7280",
        accent: "#6366f1",
        pass: "#22c55e",
        warn: "#f59e0b",
        block: "#ef4444",
      },
    },
  },
  plugins: [],
};

export default config;
