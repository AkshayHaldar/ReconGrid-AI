/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#090d16",
        surface: {
          50: "#141c2e",
          100: "#101726",
          200: "#0c121e",
          border: "#1f2c42",
          borderLight: "#2e3f5c",
        },
        brand: {
          50: "#eef2ff",
          100: "#e0e7ff",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
        },
        status: {
          matched: "#10b981",
          matchedBg: "#064e3b33",
          suggested: "#38bdf8",
          suggestedBg: "#0369a133",
          conflict: "#f59e0b",
          conflictBg: "#78350f33",
          exception: "#ef4444",
          exceptionBg: "#7f1d1d33",
          fee: "#f59e0b",
          refund: "#a855f7",
          fx: "#14b8a6",
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
