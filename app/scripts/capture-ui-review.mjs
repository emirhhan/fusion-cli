// Gerçek React önizlemelerini yerel test verisiyle görsel onaya hazırlar.
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const out = resolve('../.superpowers/sdd/2026-10-12-fusion-profesyonel-uygulama/ui-review-2026-10-15');
await mkdir(out, { recursive: true });
const scenes = [
  ['marka', '/e2e/brand-review.html'], ['ilk-karsilama', 'empty'], ['konusma', 'conversation'], ['is-yapma', 'running'], ['ekip-agent', 'team'], ['islem-onayi', 'approval'], ['model-komut', 'composer-menu'], ['skills', 'capabilities'], ['mcp-baglantilar', 'connectors'], ['kontrol-modeller', 'control'], ['ayarlar', 'settings'], ['hesap', 'account'], ['gorsel-uretim', 'image'], ['video', 'video'], ['dosyalar', 'workspace-files'], ['terminal', 'workspace-terminal'], ['gecmis', 'history-preview'], ['ilk-kurulum', 'onboarding'], ['ses-dinleme', 'voice-listening'], ['ses-dusunme', 'voice-thinking'], ['ses-onay', 'voice-approval'], ['kutuphane', 'conversation&rail=library'], ['zamanlama', 'conversation&rail=scheduled'], ['mcp-katalog', '/e2e/mcp-catalog.html'], ['destek-raporu', '/e2e/feedback-export.html'],
];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, locale: 'tr-TR', reducedMotion: 'reduce' });
const manifest = { mode: 'actual-components-test-data', approval: 'pending', screenshots: [], errors: [] };
page.on('pageerror', (error) => manifest.errors.push(error.message));
try {
  for (const theme of ['light', 'dark']) {
    for (const [name, state] of scenes) {
      const url = state.startsWith('/') ? state + '?theme=' + theme : '/e2e/preview.html?state=' + state + '&theme=' + theme + '&fullComposer=1';
      await page.goto('http://127.0.0.1:4174' + url);
      await page.evaluate((value) => { document.documentElement.dataset.theme = value; }, theme);
      await page.evaluate(async () => { await document.fonts.ready; await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))); });
      if (name === 'ekip-agent') await page.getByRole('button', { name: /Arayüz Tasarımcısı/ }).click();
      if (name === 'mcp-katalog') await page.getByRole('button', { name: 'Kataloğu aç' }).click();
      const file = `${theme}-${name}.png`;
      if (name === 'marka') {
        if (theme === 'light') await page.getByTestId('brand-native-icon').screenshot({ path: resolve(out, 'native-icon-512.png'), omitBackground: true });
        await page.getByTestId('brand-native-icon').evaluate((node) => { node.style.display = 'none'; });
      }
      await page.screenshot({ path: resolve(out, file), animations: 'disabled' });
      manifest.screenshots.push({ name, theme, file, url });
    }
  }
} finally {
  await browser.close();
  await writeFile(resolve(out, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
}
console.log(JSON.stringify({ screenshots: manifest.screenshots.length, errors: manifest.errors, out }));
