import { defineConfig, devices } from "@playwright/test";

// This suite drives the real dashboard in a real browser, so unlike the
// backend's self-contained E2E test it needs the actual backend already
// running on :8000 (uvicorn app.main:app) - only the frontend dev server
// is started automatically here.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Matches this sandbox's pre-installed browser cache. On a normal
        // machine where `playwright install` has been run for the pinned
        // @playwright/test version, this can be removed and Playwright's
        // own auto-detection takes over.
        launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE },
      },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
