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
        background: "#080c14",
        canvas: "#060910",
        surface: {
          DEFAULT: "#0f1624",
          50: "#172236",
          100: "#131b2c",
          200: "#0f1624",
          300: "#0b101b",
          border: "#1c2b42",
          borderSubtle: "#162235",
          borderStrong: "#2a3d5e",
        },
        accounting: {
          credit: "#34d399", // Emerald 400
          creditBg: "rgba(6, 78, 59, 0.3)",
          creditBorder: "rgba(5, 150, 105, 0.4)",
          debit: "#f87171", // Rose 400
          debitBg: "rgba(127, 29, 29, 0.3)",
          debitBorder: "rgba(225, 29, 72, 0.4)",
          fee: "#fbbf24", // Amber 400
          feeBg: "rgba(120, 53, 15, 0.3)",
          feeBorder: "rgba(217, 119, 6, 0.4)",
          tds: "#eab308", // Yellow 500
          tdsBg: "rgba(113, 63, 18, 0.3)",
          tdsBorder: "rgba(202, 138, 4, 0.4)",
          conflict: "#fb923c", // Orange 400
          conflictBg: "rgba(124, 45, 18, 0.35)",
          conflictBorder: "rgba(234, 88, 12, 0.45)",
          suggested: "#38bdf8", // Sky 400
          suggestedBg: "rgba(3, 105, 161, 0.25)",
          suggestedBorder: "rgba(2, 132, 199, 0.4)",
          exception: "#f43f5e", // Rose 500
          exceptionBg: "rgba(159, 18, 57, 0.3)",
          exceptionBorder: "rgba(225, 29, 72, 0.45)",
          refund: "#c084fc", // Purple 400
          refundBg: "rgba(88, 28, 135, 0.3)",
          refundBorder: "rgba(147, 51, 234, 0.4)",
          batched: "#818cf8", // Indigo 400
          batchedBg: "rgba(49, 46, 129, 0.3)",
          batchedBorder: "rgba(79, 70, 229, 0.4)",
          fx: "#2dd4bf", // Teal 400
          fxBg: "rgba(19, 78, 74, 0.3)",
          fxBorder: "rgba(13, 148, 136, 0.4)",
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
