import { defineConfig, devices } from "@playwright/test";

/** End-to-end tests (Section 5.4). Expects the API on :8000 and the web app on :3000. */
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "off",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: /approvals-pwa/ },
    { name: "phone", use: { ...devices["Pixel 7"] }, testMatch: /approvals-pwa/ },
  ],
});
