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

test('geciken Fusion işi sırasında sohbet yanıtlanır, söz kesilince iş sürer', async ({ page }) => {
  await page.goto('/tests/browser/voice.html?delay');
  await page.getByRole('button', { name: 'Başlat', exact: true }).click();
  await fixture(page, 'ready');
  await expect(page.getByLabel('Ses durumu')).toHaveText('active');
  await fixture(page, 'utter');
  const invoke = (action: string) => page.evaluate(action => {
    const live = (window as unknown as { voiceFixture: Record<string, () => void> }).voiceFixture;
    live[action]();
  }, action);
  const played = () => page.evaluate(() => (window as unknown as { voiceFixture: Fixture }).voiceFixture.spoken);
  await expect.poll(played).toEqual(['Bir saniye, Fusion’a sorayım.']);
  await invoke('barge');
  await expect(page.getByLabel('Kullanıcı sözü')).toHaveText('Dur perşembe demek istedim');
  await invoke('talk');
  await expect.poll(played).toEqual(['Bir saniye, Fusion’a sorayım.', 'İyiyim, teşekkür ederim.']);
  await invoke('finishSpeech');
  await expect.poll(async () => (await played()).at(-1)).toBe('Sen nasılsın?');
  await invoke('finishSpeech');
  await invoke('finishAnswer');
  await expect.poll(async () => (await played()).at(-1)).toBe('Birinci cümle.');
  expect(await page.evaluate(() => (window as unknown as { voiceFixture: { utterances: number } }).voiceFixture.utterances)).toBe(1);
});
