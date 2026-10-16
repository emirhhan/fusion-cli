import { test, expect } from "@playwright/test";
for (const theme of ["dark", "light"]) for (const [width, height] of [[320,360],[380,460],[1440,833]]) {
 test(`izin kartı ${theme} ${width}x${height}`, async ({ page }, info) => {
  await page.setViewportSize({ width, height });
  await page.goto(`/e2e/permission-fit.html?theme=${theme}`);
  const dialog = page.getByRole("dialog");
  const box = await dialog.boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(0); expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x+box!.width).toBeLessThanOrEqual(width); expect(box!.y+box!.height).toBeLessThanOrEqual(height);
  expect(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await page.getByRole("button", { name: "Şimdi değil" }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "Şimdi değil" })).toBeInViewport();
  await page.screenshot({ path: info.outputPath(`permission-${theme}-${width}.png`), animations: "disabled" });
 });
}
