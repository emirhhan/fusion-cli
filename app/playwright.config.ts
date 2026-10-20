import { defineConfig } from "@playwright/test";

export default defineConfig({
  expect: { toHaveScreenshot: { animations: "disabled", maxDiffPixelRatio: 0.01 } },
  fullyParallel: false,
  testDir: "./e2e",
  testMatch: "**/*.visual.ts",
  use: {
    baseURL: "http://127.0.0.1:4174",
    colorScheme: "light",
    locale: "tr-TR",
    reducedMotion: "reduce",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4174",
    reuseExistingServer: false,
    timeout: 30_000,
    url: "http://127.0.0.1:4174/e2e/preview.html",
  },
});
