import { defineConfig, devices } from "@playwright/test";

/** Browser tests in sample-data mode: no server needed. API mode: playwright.api.config.mts. */
// Its own variable and no server reuse: the tests always run against a fresh build of this tree.
const port = Number(process.env.DASHBOARD_E2E_PORT ?? 3100);

export default defineConfig({
  testDir: "./e2e/mock",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report/mock" }]],
  outputDir: "test-results/mock",
  use: { baseURL: `http://localhost:${port}`, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: `npm run build && npm run start -- --port ${port}`,
    env: { NEXT_PUBLIC_DATA_SOURCE: "mock", NEXT_DIST_DIR: ".next-e2e-mock" },
    url: `http://localhost:${port}/login`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
