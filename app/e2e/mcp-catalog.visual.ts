import { expect, test } from '@playwright/test';
test('MCP kataloğu dar pencerede okunur ve Escape odağı geri verir', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto('/e2e/mcp-catalog.html');
  await page.getByRole('button', { name: 'Kataloğu aç' }).click();
  const dialog = page.getByRole('dialog', { name: 'server araç kataloğu' });
  await expect(dialog.getByText('Değişiklik yapabilir', { exact: true })).toBeVisible();
  await dialog.getByText('Parametre ayrıntıları', { exact: true }).click();
  await expect(dialog.getByText('query', { exact: true })).toBeVisible();
  expect(await dialog.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Kataloğu aç' })).toBeFocused();
});
