import { test, expect } from "@playwright/test";
for (const theme of ["dark", "light"]) for (const width of [320,390,1440]) {
 test(`işe mesaj seçimi ${theme} ${width}`, async ({ page }, info) => {
  await page.setViewportSize({ width, height: 720 });
  await page.goto(`/e2e/composer-running.html?theme=${theme}`);
  const select = page.getByLabel("Çalışan işe mesaj");
  await expect(select).toBeVisible();
  expect(await select.evaluate(el => !!el.closest(".composer"))).toBe(true);
  const box=await select.boundingBox(); const parent=await page.locator(".composer").boundingBox();
  expect(box!.x).toBeGreaterThanOrEqual(parent!.x);
  expect(box!.x+box!.width).toBeLessThanOrEqual(parent!.x+parent!.width);
  const input=await page.getByRole("textbox", { name: "Mesaj" }).boundingBox();
  expect(input!.y).toBeGreaterThanOrEqual(box!.y+box!.height);
  await select.selectOption("queue");
  await expect(select).toHaveValue("queue");
  expect(await page.locator("body").evaluate(el => el.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("composer.png"), animations: "disabled" });
 });
}
