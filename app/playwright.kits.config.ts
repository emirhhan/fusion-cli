import { defineConfig } from '@playwright/test';
import { resolve } from 'node:path';
export default defineConfig({
  testDir: './e2e', testMatch: '**/kits-*.browser.ts', fullyParallel: false,
  use: { baseURL: 'http://127.0.0.1:15175', locale: 'tr-TR' },
  webServer: { command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 15175', cwd: resolve(import.meta.dirname, '../../fusion-kits'), url: 'http://127.0.0.1:15175/tests/browser/space.html', reuseExistingServer: false, timeout: 30000 },
});
