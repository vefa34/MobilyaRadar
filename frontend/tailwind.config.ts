import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: "media",
  theme: { extend: { colors: { brand: { DEFAULT: "#1f3a5f", light: "#2a78d6" } } } },
  plugins: [],
};
export default config;
