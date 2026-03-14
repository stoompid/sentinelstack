import type { Config } from "tailwindcss"

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "#080a0f",
          surface: "#0f1219",
          card: "#141820",
          border: "#1e2535",
          hover: "#1a2030",
        },
        accent: {
          blue: "#3b82f6",
          "blue-dim": "#1d4ed8",
          "blue-glow": "rgba(59,130,246,0.15)",
        },
        tier: {
          flash: "#ef4444",
          "flash-dim": "rgba(239,68,68,0.15)",
          "flash-border": "rgba(239,68,68,0.4)",
          priority: "#f59e0b",
          "priority-dim": "rgba(245,158,11,0.15)",
          "priority-border": "rgba(245,158,11,0.4)",
          routine: "#06b6d4",
          "routine-dim": "rgba(6,182,212,0.15)",
          "routine-border": "rgba(6,182,212,0.4)",
        },
        text: {
          primary: "#e2e8f0",
          muted: "#64748b",
          dim: "#334155",
        },
      },
      fontFamily: {
        mono: ["var(--font-mono)", "JetBrains Mono", "monospace"],
        sans: ["var(--font-sans)", "Inter", "sans-serif"],
      },
      animation: {
        "flash-pulse": "flash-pulse 2s ease-in-out infinite",
        "fade-in": "fade-in 0.3s ease-out",
        "slide-in": "slide-in 0.2s ease-out",
      },
      keyframes: {
        "flash-pulse": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(239,68,68,0)" },
          "50%": { boxShadow: "0 0 12px 4px rgba(239,68,68,0.3)" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in": {
          from: { transform: "translateX(-8px)", opacity: "0" },
          to: { transform: "translateX(0)", opacity: "1" },
        },
      },
    },
  },
  plugins: [],
}

export default config
