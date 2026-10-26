import { defineConfig, devices } from "@playwright/test";

/** Browser tests in API mode, against a cloud stack seeded with seed-dev; run through
 * scripts/api-e2e.sh, which brings that stack up and sets the variables below. */
const port = Number(process.env.DASHBOARD_E2E_PORT ?? 3101);

export default defineConfig({
  testDir: "./e2e/api",
  workers: 1, // one ZITADEL, one seeded world
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report/api" }]],
  outputDir: "test-results/api",
  timeout: 60_000,
  use: { baseURL: `http://localhost:${port}`, trace: "retain-on-failure", ...devices["Desktop Chrome"] },
  webServer: {
    command: `npm run build && npm run start -- --port ${port}`,
    env: { NEXT_PUBLIC_DATA_SOURCE: "api", NEXT_PUBLIC_API_URL: process.env.E2E_API_URL ?? "", NEXT_DIST_DIR: ".next-e2e-api" },
    url: `http://localhost:${port}/login`,
    reuseExistingServer: false,
    timeout: 180_000,
  },
});
