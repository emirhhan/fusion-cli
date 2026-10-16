import { expect, test } from '@playwright/test';
test('F işaretinin köşeleri gerçekten saydamdır', async ({ page }) => {
  await page.goto('/e2e/brand-review.html');
  const pixels = await page.locator('img.fusion-logo').first().evaluate(async (node) => {
    const image = node as HTMLImageElement;
    await image.decode();
    const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 128;
    const context = canvas.getContext('2d')!; context.drawImage(image, 0, 0, 128, 128);
    const data = context.getImageData(0, 0, 128, 128).data;
    return { corners: [0, 127, 127 * 128, 128 * 128 - 1].map((i) => data[i * 4 + 3]), colored: Array.from(data).filter((_v, i) => i % 4 === 3 && data[i] > 0).length };
  });
  expect(pixels.corners).toEqual([0, 0, 0, 0]);
  expect(pixels.colored).toBeGreaterThan(1000);
});
test('azaltılmış hareket animasyonu durdurur ve iş bitince orbit kaldırılır', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/e2e/brand-review.html');
  const orbit = page.locator('.fusion-loading-mark__orbit');
  await expect(orbit).toHaveCount(1);
  expect(await orbit.evaluate((node) => getComputedStyle(node).animationName)).toBe('none');
  await page.getByRole('button', { name: 'Yüklemeyi bitir / başlat' }).click();
  await expect(orbit).toHaveCount(0);
  await expect(page.locator('.runtime-setup__mark .fusion-logo')).toHaveCount(1);
});
test('Inter ve JetBrains Mono gerçek paket fontlarıyla çizilir', async ({ page }) => {
  await page.goto('/e2e/brand-review.html');
  await page.evaluate(async () => { await document.fonts.ready; });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('DOM.enable'); await cdp.send('CSS.enable');
  const { root } = await cdp.send('DOM.getDocument');
  for (const [selector, family] of [['[data-testid="inter-sample"]', 'Inter'], ['[data-testid="mono-sample"]', 'JetBrains']]) {
    const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: root.nodeId, selector });
    const { fonts } = await cdp.send('CSS.getPlatformFontsForNode', { nodeId });
    expect(fonts.some((font: { familyName: string; isCustomFont: boolean }) => font.isCustomFont && font.familyName.includes(family))).toBe(true);
  }
});
