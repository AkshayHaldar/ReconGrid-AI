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
        background: "#090a0f",
        canvas: "#090a0f",
        surface: {
          DEFAULT: "#111318",
          50: "#1c202a",
          100: "#151820",
          200: "#111318",
          300: "#0c0e12",
          border: "#1e222d",
          borderSubtle: "#161922",
          borderStrong: "#282e3d",
        },
        accounting: {
          credit: "#34d399", // Emerald 400
          creditBg: "rgba(6, 78, 59, 0.25)",
          creditBorder: "rgba(5, 150, 105, 0.35)",
          debit: "#f87171", // Rose 400
          debitBg: "rgba(127, 29, 29, 0.25)",
          debitBorder: "rgba(225, 29, 72, 0.35)",
          fee: "#fbbf24", // Amber 400
          feeBg: "rgba(120, 53, 15, 0.25)",
          feeBorder: "rgba(217, 119, 6, 0.35)",
          tds: "#eab308", // Yellow 500
          tdsBg: "rgba(113, 63, 18, 0.25)",
          tdsBorder: "rgba(202, 138, 4, 0.35)",
          conflict: "#fb923c", // Orange 400
          conflictBg: "rgba(124, 45, 18, 0.25)",
          conflictBorder: "rgba(234, 88, 12, 0.35)",
          suggested: "#38bdf8", // Sky 400
          suggestedBg: "rgba(3, 105, 161, 0.2)",
          suggestedBorder: "rgba(2, 132, 199, 0.35)",
          exception: "#f43f5e", // Rose 500
          exceptionBg: "rgba(159, 18, 57, 0.25)",
          exceptionBorder: "rgba(225, 29, 72, 0.35)",
          refund: "#c084fc", // Purple 400
          refundBg: "rgba(88, 28, 135, 0.25)",
          refundBorder: "rgba(147, 51, 234, 0.35)",
          batched: "#818cf8", // Indigo 400
          batchedBg: "rgba(49, 46, 129, 0.25)",
          batchedBorder: "rgba(79, 70, 229, 0.35)",
          fx: "#2dd4bf", // Teal 400
          fxBg: "rgba(19, 78, 74, 0.25)",
          fxBorder: "rgba(13, 148, 136, 0.35)",
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        xs: "0 1px 2px 0 rgba(0, 0, 0, 0.25)",
      },
    },
  },
  plugins: [],
};
