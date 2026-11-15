import { expect, test } from "@playwright/test";

const user = ".conversation__bubble";
const assistant = ".conversation__message--assistant .markdown";

test("yanıt ve kullanıcı metni aynı küçük punto ve normal ağırlığı paylaşır", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/e2e/preview.html?state=typography&inspector=0&sidebar=0");
  await expect(page.locator(`${assistant} h1`)).toBeVisible();
  await page.evaluate(async () => { await document.fonts.ready; });

  const bubble = page.locator(user);
  await expect(bubble).toHaveCSS("font-size", "13px");
  await expect(bubble).toHaveCSS("font-weight", "400");
  await expect(bubble).toHaveCSS("line-height", "19.5px");
  const userFamily = await bubble.evaluate(node => getComputedStyle(node).fontFamily);
  expect(userFamily).toMatch(/^Inter,/);
  for (const prose of await page.locator(assistant).all()) {
    await expect(prose).toHaveCSS("font-family", userFamily);
    await expect(prose).toHaveCSS("font-size", "13px");
    await expect(prose).toHaveCSS("font-weight", "400");
    await expect(prose).toHaveCSS("line-height", "19.5px");
  }
  await expect(page.locator(`${assistant} strong`)).toHaveCSS("font-weight", "600");
  await expect(page.locator(`${assistant} em`)).toHaveCSS("font-style", "italic");
  await expect(page.locator(`${assistant} table`)).toHaveCSS("font-size", "13px");

  await page.locator(".app-shell__main").evaluate(node => { (node as HTMLElement).style.width = "600px"; });
  for (const prose of await page.locator(assistant).all()) {
    await expect(prose).toHaveCSS("font-size", "13px");
  }
  await page.evaluate(() => { document.documentElement.style.fontSize = "125%"; });
  for (const text of await page.locator(`${user}, ${assistant}`).all()) {
    await expect(text).toHaveCSS("font-size", "16.25px");
    await expect(text).toHaveCSS("line-height", "24.375px");
    await expect(text).toHaveCSS("font-weight", "400");
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test("ayrı işlem penceresi açılınca satırlar büyümez", async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 900 });
  await page.goto("/e2e/preview.html?state=activity-panel&count=3&empty=1");
  const first = page.getByText("İşlem 1", { exact: true });
  await first.scrollIntoViewIfNeeded();
  await expect(first).toHaveCSS("font-size", "13px");
  const family = await first.evaluate(node => getComputedStyle(node).fontFamily);
  await first.click();
  const panel = page.getByRole("region", { name: "İşlem ayrıntıları" });
  await expect(panel).toBeVisible();
  await expect(panel.getByText("İşlem 1", { exact: true })).toHaveCSS("font-size", "13px");
  await expect(panel.getByText("İşlem 1", { exact: true })).toHaveCSS("font-family", family);
  await expect(panel.getByText("İşlem 1", { exact: true })).toHaveCSS("font-weight", "400");
});
