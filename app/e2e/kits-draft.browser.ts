import { expect, test } from '@playwright/test';
test('yerel taslak StrictMode altında yeniden yüklenir ve başka hesaba taşınmaz', async ({ page }) => {
  await page.goto('/tests/browser/draft.html');
  await page.getByLabel('Taslak metni').fill('Uygulama yeniden açıldığında koru');
  await expect.poll(() => page.evaluate(() => Object.values(localStorage).some((value) => value.includes('Uygulama yeniden açıldığında koru')))).toBe(true);
  await page.reload();
  await expect(page.getByLabel('Taslak metni')).toHaveValue('Uygulama yeniden açıldığında koru');
  await page.goto('/tests/browser/draft.html?owner=owner-b');
  await expect(page.getByLabel('Taslak metni')).toHaveValue('Başlangıç');
  await page.goto('/tests/browser/draft.html');
  await expect(page.getByLabel('Taslak metni')).toHaveValue('Uygulama yeniden açıldığında koru');
});
