import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          50: "#eef2fb",
          100: "#d6deef",
          200: "#a8b6d8",
          300: "#7484bb",
          400: "#4f5e9a",
          500: "#384574",
          600: "#2a335a",
          700: "#1f2545",
          800: "#161a32",
          900: "#0d1024",
          950: "#070918",
        },
        accent: {
          400: "#6ea8ff",
          500: "#3a82f7",
          600: "#1f63d4",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        display: ['"Fraunces"', "Georgia", "serif"],
      },
      boxShadow: {
        card: "0 1px 0 rgb(255 255 255 / 0.04), 0 8px 32px rgb(0 0 0 / 0.40)",
      },
    },
  },
  plugins: [],
};
export default config;
