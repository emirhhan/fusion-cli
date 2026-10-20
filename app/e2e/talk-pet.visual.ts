import { test, expect } from "@playwright/test";
for (const theme of ["dark", "light"]) for (const wide of [false, true]) {
 test(`yalnız karakter ${theme} ${wide}`, async ({ page }, info) => {
  await page.setViewportSize({ width: wide ? 380 : 260, height: wide ? 460 : 360 });
  await page.goto(`/e2e/talk-pet.html?theme=${theme}&wide=${wide ? 1 : 0}`);
  const character = page.getByRole("button", { name: /Fusion.*dinle/i });
  await expect(character).toBeVisible();
  const bounds = await page.locator(".fusion-avatar__glow").boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(wide ? 380 : 260);
  const rect = await character.boundingBox();
  await page.mouse.move(rect!.x + rect!.width / 2, rect!.y + rect!.height / 2);
  await page.mouse.down();
  await page.mouse.move(rect!.x + rect!.width / 2 + 24, rect!.y + rect!.height / 2 + 18, {steps: 3});
  await page.mouse.up();
  expect(await page.locator("body").getAttribute("data-drags")).toBe("1");
  expect(await page.locator("body").getAttribute("data-listens")).toBeNull();
  await character.click();
  expect(await page.locator("body").getAttribute("data-listens")).toBe("1");
  await character.hover();
  await expect(page.locator("header, footer")).toHaveCount(0);
  await page.screenshot({ path: info.outputPath("character.png"), animations: "disabled", omitBackground: true });
  await character.click({ button: "right" });
  await expect(page.getByRole("menuitem")).toHaveCount(3);
  const menu = await page.getByRole("menu").boundingBox();
  expect(menu!.x).toBeGreaterThanOrEqual(0);
  expect(menu!.x + menu!.width).toBeLessThanOrEqual(wide ? 380 : 260);
  await page.screenshot({ path: info.outputPath("menu.png"), animations: "disabled", omitBackground: true });
  await page.goto(`/e2e/talk-pet.html?theme=${theme}&wide=${wide ? 1 : 0}&error=1`);
  await expect(page.getByRole("alert")).toBeVisible();
  expect(await page.locator("body").evaluate(el => el.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("error.png"), animations: "disabled", omitBackground: true });
 });
}
