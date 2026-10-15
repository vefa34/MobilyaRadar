import { defineConfig } from "@playwright/test";

// Requires backend (:8000, DEMO_MODE=true) and frontend (:3000) running — see README.
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
    screenshot: "only-on-failure",
  },
});
