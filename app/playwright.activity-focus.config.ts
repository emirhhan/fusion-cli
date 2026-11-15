import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config";

/** macOS WebView için odak sözleşmesi; CDP/font ve tarayıcıya özel görüntü testleri hariç. */
export default defineConfig({
  ...baseConfig,
  testMatch: "**/activity-panel.visual.ts",
  grep: /gerçek Composer|odaktaki satır|kullanıcı isteğiyle panel açma/,
  workers: 1,
  projects: [
    { name: "chromium-focus", use: { browserName: "chromium" } },
    { name: "webkit-focus", use: { browserName: "webkit" } },
  ],
});
