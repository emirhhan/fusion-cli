// "Nasıl yapılır" ve kurulum eğitiminin ekran görüntülerini çalışan arayüzden alır.
// Gerçek bileşenler, sentetik test verisiyle (kişisel veri/anahtar yok) çizilir.
// Kullanım: npm run dev -- --host 127.0.0.1 --port 4174  ->  node scripts/capture-guide.mjs
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';

const base = process.env.GUIDE_BASE ?? 'http://127.0.0.1:4174';
const out = resolve('public/guide');
const tmp = resolve(process.env.GUIDE_TMP ?? '/tmp/fusion-guide');
await mkdir(out, { recursive: true });
await mkdir(tmp, { recursive: true });

const preview = (state, extra = '') => `/e2e/preview.html?state=${state}&theme=light${extra}`;
const settings = (section) => async (page) => {
  await page.getByRole('button', { name: section, exact: true }).click();
  await page.waitForTimeout(700);
};
// [dosya adı, adres, sayfa hazırlığı]
const scenes = [
  ['ana-menu', preview('empty', '&rail=home')],
  ['sohbet', preview('conversation')],
  ['onay', preview('approval')],
  ['saglayici', preview('control')],
  ['dosyalar', preview('workspace-files')],
  ['terminal', preview('workspace-terminal')],
  ['gecmis', preview('history-preview')],
  ['gorsel', preview('image')],
  ['kitaplik', preview('conversation', '&rail=library')],
  ['zamanlanan', preview('conversation', '&rail=scheduled')],
  ['kits-menu', preview('conversation', '&rail=kits')],
  ['beceriler', preview('capabilities')],
  ['baglayicilar', preview('connectors')],
  ['ekip', preview('team')],
  ['ayar-genel', preview('settings')],
  ['ayar-ses', preview('settings'), settings('Ses')],
  ['ayar-kisisel', preview('settings'), settings('Kişiselleştirme')],
  ['ayar-modeller', preview('settings'), settings('Modeller')],
  ['ayar-tarayici', preview('settings'), settings('Tarayıcı')],
  ['ayar-izinler', preview('settings'), settings('İzinler')],
  ['ayar-uzak', preview('settings'), settings('Uzaktan Erişim')],
  ['ayar-guncelleme', preview('settings'), settings('Güncellemeler')],
  ['kurulum', '/e2e/onboarding-flow.html?theme=light&step=welcome'],
];

const only = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'tr-TR', reducedMotion: 'reduce' });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
try {
  for (const [name, url, prepare] of scenes) {
    if (only.length && !only.includes(name)) continue;
    await page.goto(base + url);
    await page.evaluate(async () => { await document.fonts.ready; });
    if (prepare) await prepare(page);
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const png = resolve(tmp, `${name}.png`);
    await page.screenshot({ path: png, animations: 'disabled' });
    // 1440 -> 960 genişlik, webp q78: tipik dosya 20-60 KB.
    execFileSync('cwebp', ['-quiet', '-q', '78', '-resize', '960', '0', png, '-o', resolve(out, `${name}.webp`)]);
    console.log('ok', name);
  }
} finally {
  await browser.close();
}
if (errors.length) { console.error('sayfa hataları:', errors); process.exitCode = 1; }
