/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        ink: {
          50: "#f5f7fa",
          100: "#e4e9f0",
          200: "#c8d1de",
          300: "#a5b1c2",
          500: "#5a6678",
          700: "#2d3848",
          900: "#0e131c",
          950: "#070a10",
        },
        signal: {
          good: "#3aaf6a",
          warn: "#d8a72b",
          bad: "#c0392b",
          calm: "#4a7ce0",
        },
      },
    },
  },
  plugins: [],
};
