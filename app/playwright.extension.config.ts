import { defineConfig } from "@playwright/test";

// Eklenti uçtan uca testi: gerçek Chromium + yüklü Fusion Browser eklentisi, yerel test sitesi.
// Çalıştır: npx playwright test -c playwright.extension.config.ts
export default defineConfig({
  fullyParallel: false,
  testDir: "./e2e",
  testMatch: "**/*.extension.ts",
  timeout: 90_000,
  workers: 1,
});
