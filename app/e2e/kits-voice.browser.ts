import { expect, test } from '@playwright/test';
type Fixture = { detects: number; spoken: string[]; closed: number; ready(): void; utter(): void; stale(): void };
const fixture = (page: import('@playwright/test').Page, action: 'ready' | 'utter' | 'stale') => page.evaluate((action) => (window as unknown as { voiceFixture: Fixture }).voiceFixture[action](), action);
test('aynı anda iki başlat tek motor tespiti yapar', async ({ page }) => {
  await page.goto('/tests/browser/voice.html');
  await page.getByRole('button', { name: 'Başlat', exact: true }).evaluate((button) => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  expect(await page.evaluate(() => (window as unknown as { voiceFixture: Fixture }).voiceFixture.detects)).toBe(1);
});
test('bağlanırken bitir geç gelen motoru kapatır', async ({ page }) => {
  await page.goto('/tests/browser/voice.html');
  await page.getByRole('button', { name: 'Başlat', exact: true }).click();
  await page.getByRole('button', { name: 'Bitir', exact: true }).click();
  await fixture(page, 'ready');
  await expect(page.getByLabel('Ses durumu')).toHaveText('idle');
  await expect.poll(() => page.evaluate(() => (window as unknown as { voiceFixture: Fixture }).voiceFixture.closed)).toBe(1);
});
test('sözünü kes kalan cümleleri tekrar başlatmaz', async ({ page }) => {
  await page.goto('/tests/browser/voice.html');
  await page.getByRole('button', { name: 'Başlat', exact: true }).click();
  await fixture(page, 'ready');
  await expect(page.getByLabel('Ses durumu')).toHaveText('active');
  await fixture(page, 'utter');
  await expect.poll(() => page.evaluate(() => (window as unknown as { voiceFixture: Fixture }).voiceFixture.spoken.length)).toBe(1);
  await page.getByRole('button', { name: 'Sözünü kes', exact: true }).click();
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  expect(await page.evaluate(() => (window as unknown as { voiceFixture: Fixture }).voiceFixture.spoken.length)).toBe(1);
});
test('bitmiş aramanın dinleyicisi altyazıyı değiştirmez', async ({ page }) => {
  await page.goto('/tests/browser/voice.html');
  await page.getByRole('button', { name: 'Başlat', exact: true }).click(); await fixture(page, 'ready');
  await expect(page.getByLabel('Ses durumu')).toHaveText('active');
  await page.getByRole('button', { name: 'Bitir', exact: true }).click();
  await fixture(page, 'stale');
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByLabel('Kullanıcı sözü')).toHaveText('');
});
test('mikrofon susturulduktan sonra eski final sözü gönderilmez', async ({ page }) => {
  await page.goto('/tests/browser/voice.html');
  await page.getByRole('button', { name: 'Başlat', exact: true }).click(); await fixture(page, 'ready');
  await expect(page.getByLabel('Ses durumu')).toHaveText('active');
  await page.getByRole('button', { name: 'Mikrofonu sustur', exact: true }).click();
  await fixture(page, 'utter');
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  expect(await page.evaluate(() => (window as unknown as { voiceFixture: { utterances: number } }).voiceFixture.utterances)).toBe(0);
});
