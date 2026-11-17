import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config";

export default defineConfig({
  ...baseConfig,
  testMatch: "**/activity-panel-geometry.visual.ts",
  workers: 1,
  projects: [
    { name: "chromium-geometry", use: { browserName: "chromium" } },
    { name: "webkit-geometry", use: { browserName: "webkit" } },
  ],
});
