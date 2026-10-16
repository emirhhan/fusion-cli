import { expect, test } from '@playwright/test';
const counts = (page: import('@playwright/test').Page, method: string) => page.evaluate((method) => (window as unknown as { spaceFixture: { requests: { method: string }[] } }).spaceFixture.requests.filter((item) => item.method === method).length, method);
test('geciken sayfa taramasında tek istek uçuşta kalır', async ({ page }) => {
  await page.clock.install();
  await page.goto('/tests/browser/space.html');
  await expect.poll(() => counts(page, 'GET')).toBe(1);
  await page.clock.runFor(9000);
  expect(await counts(page, 'GET')).toBe(1);
});
test('hızlı çift sayfa oluşturma tek mutasyon gönderir', async ({ page }) => {
  await page.goto('/tests/browser/space.html');
  await page.locator('header').getByRole('button', { name: 'Yeni sayfa', exact: true }).evaluate((button) => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click(); });
  expect(await counts(page, 'POST')).toBe(1);
});
test('eski alanda geciken create yeni alanda gezinme başlatmaz', async ({ page }) => {
  await page.goto('/tests/browser/space.html');
  await page.locator('header').getByRole('button', { name: 'Yeni sayfa', exact: true }).click();
  await expect.poll(() => counts(page, 'POST')).toBe(1);
  await page.getByRole('button', { name: 'Alan B', exact: true }).click();
  await page.evaluate(async () => { (window as unknown as { spaceFixture: { finishCreates: () => void } }).spaceFixture.finishCreates(); await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))); });
  await expect(page.getByLabel('Seçilen sayfa')).toHaveText('yok');
});
test('alan değişince eski liste isteği abort edilir', async ({ page }) => {
  await page.goto('/tests/browser/space.html');
  await expect.poll(() => counts(page, 'GET')).toBe(1);
  await page.getByRole('button', { name: 'Alan B', exact: true }).click();
  expect(await page.evaluate(() => (window as unknown as { spaceFixture: { requests: { signal?: AbortSignal }[] } }).spaceFixture.requests[0].signal?.aborted === true)).toBe(true);
});
