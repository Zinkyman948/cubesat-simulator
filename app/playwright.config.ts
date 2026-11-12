import { defineConfig, devices } from "@playwright/test";

// End-to-end tests: the built frontend (served by `vite preview` with the
// app's Content Security Policy) against a real engine. Run `npm run build`
// first, and have `simcore` on PATH (activate the Python venv).
export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: "http://localhost:1420",
    viewport: { width: 1600, height: 1000 },
    trace: "retain-on-failure",
    launchOptions: {
      // Software WebGL so the Cesium globe renders on machines without a GPU.
      args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
    },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 1000 } } }],
  webServer: [
    {
      command: "simcore serve --port 8765",
      url: "http://127.0.0.1:8765/api/health",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npx vite preview",
      url: "http://localhost:1420",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
