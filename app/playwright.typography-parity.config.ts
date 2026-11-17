import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config";

export default defineConfig({
  ...baseConfig,
  testMatch: "**/typography-parity.visual.ts",
  workers: 1,
  projects: [
    { name: "chromium-typography", use: { browserName: "chromium" } },
    { name: "webkit-typography", use: { browserName: "webkit" } },
  ],
});
