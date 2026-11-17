import { expect, test, type Page } from "@playwright/test";

async function open(page: Page, query = "") {
  await page.setViewportSize({ width: 1100, height: 900 });
  await page.goto(`/e2e/preview.html?state=activity-panel&${query}`);
  await page.evaluate(async () => { await document.fonts.ready; });
}
const outerTop = (page: Page) => page.locator(".conversation").evaluate(node => node.scrollTop);

test("gerçek tekerlek panelde ve sınırlarda ana sohbeti hareket ettirmez", async ({ page }) => {
  await open(page);
  const first = page.getByText("İşlem 1", { exact: true });
  await first.scrollIntoViewIfNeeded();
  await first.click();
  const panel = page.getByRole("region", { name: "İşlem ayrıntıları" });
  const scroll = panel.locator(".work-activity-panel__scroll");
  await expect(panel).toBeVisible();
  await scroll.evaluate(node => node.scrollTop = 0);
  const top = await outerTop(page);
  await scroll.hover({ position: { x: 1, y: 200 } });
  await page.mouse.wheel(0, 240);
  await expect.poll(() => scroll.evaluate(node => node.scrollTop)).toBeGreaterThan(0);
  expect(await outerTop(page)).toBe(top);
  await scroll.evaluate(node => node.scrollTop = node.scrollHeight);
  const bottom = await scroll.evaluate(node => node.scrollTop);
  await page.mouse.wheel(0, 900);
  await page.waitForTimeout(180);
  expect(await scroll.evaluate(node => node.scrollTop)).toBe(bottom);
  expect(await outerTop(page)).toBe(top);
  await scroll.evaluate(node => node.scrollTop = 0);
  await page.mouse.wheel(0, -900);
  await page.waitForTimeout(180);
  expect(await outerTop(page)).toBe(top);
  const output = panel.locator("details[open] .activity__trail-output");
  await output.hover();
  await output.evaluate(node => node.scrollTop = node.scrollHeight);
  const beforeOutputWheel = await outerTop(page);
  await page.mouse.wheel(0, 900);
  await page.waitForTimeout(180);
  expect(await outerTop(page)).toBe(beforeOutputWheel);
  // Başlık ve kaydırılamayan alan da ana sohbetin tekerleğini devralmaz.
  await panel.locator(".work-activity-panel__header").hover();
  await page.mouse.wheel(0, 500);
  await page.waitForTimeout(180);
  expect(await outerTop(page)).toBe(beforeOutputWheel);
});

test("klavye, akışta üçüncü işlem, yeni satır ve sohbet yalıtımı", async ({ page }) => {
  await open(page, "count=2");
  const second = page.getByText("İşlem 2", { exact: true });
  await second.scrollIntoViewIfNeeded();
  await second.locator("xpath=ancestor::summary").focus();
  await page.keyboard.press("Enter");
  await expect(second.locator("xpath=ancestor::details")).toHaveAttribute("open", "");
  await page.getByRole("button", { name: "İşlem ekle" }).click();
  const panel = page.getByRole("region", { name: "İşlem ayrıntıları" });
  await expect(panel.getByText("İşlem 3", { exact: true })).toBeVisible();
  await expect(panel.getByText("İşlem 2", { exact: true }).locator("xpath=ancestor::details")).toHaveAttribute("open", "");
  await page.getByRole("button", { name: "İşlem ekle" }).click();
  await expect(panel.getByText("İşlem 4", { exact: true })).toBeVisible();
  await expect(panel.getByText("İşlem 2", { exact: true }).locator("xpath=ancestor::details")).toHaveAttribute("open", "");
  await panel.getByText("İşlem 2", { exact: true }).locator("xpath=ancestor::summary").focus();
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await expect(page.getByText("İşlem 2", { exact: true }).locator("xpath=ancestor::summary")).toBeFocused();
  await page.keyboard.press("Space");
  await expect(panel).toBeVisible();
  await page.getByRole("button", { name: "Sohbet değiştir" }).click();
  await expect(panel).toHaveCount(0);
  await expect(page.locator(".activity__trail-item")).toHaveCount(2);
});

for (const theme of ["light", "dark"]) {
  test(`panel görünümü ${theme} geniş ve dar`, async ({ page }) => {
    await open(page, `theme=${theme}`);
    await page.getByText("İşlem 2", { exact: true }).click();
    const panel = page.getByRole("region", { name: "İşlem ayrıntıları" });
    await panel.scrollIntoViewIfNeeded();
    await expect(panel).toHaveScreenshot(`activity-panel-${theme}.png`);
    await page.setViewportSize({ width: 430, height: 800 });
    await expect(page.locator(".conversation")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(panel).toHaveScreenshot(`activity-panel-${theme}-narrow.png`);
  });
}

test("en alttaki kullanıcı panel açınca otomatik alta çekilmez", async ({ page }) => {
  await open(page, "tail=0");
  await expect(page.getByText("Sonuç hazır.", { exact: true })).toBeVisible();
  const top = await outerTop(page);
  await page.getByText("İşlem 1", { exact: true }).click();
  await expect(page.getByRole("region", { name: "İşlem ayrıntıları" })).toBeVisible();
  await page.waitForTimeout(200);
  expect(await outerTop(page)).toBe(top);
});

test("kaydırılamayacak kadar kısa panelde tekerlek sohbeti devralmaz", async ({ page }) => {
  await open(page, "count=3&empty=1");
  await page.getByText("İşlem 1", { exact: true }).click();
  const panel = page.getByRole("region", { name: "İşlem ayrıntıları" });
  const scroll = panel.locator(".work-activity-panel__scroll");
  await scroll.hover();
  expect(await scroll.evaluate(node => node.scrollHeight <= node.clientHeight)).toBe(true);
  const top = await outerTop(page);
  await page.mouse.wheel(0, 800);
  await page.waitForTimeout(180);
  expect(await outerTop(page)).toBe(top);
  await page.mouse.wheel(0, -800);
  await page.waitForTimeout(180);
  expect(await outerTop(page)).toBe(top);
});

test("üçüncü işlem gelişi panel dışındaki klavye odağını çalmaz", async ({ page }) => {
  await open(page, "count=2");
  await page.getByText("İşlem 2", { exact: true }).click();
  const append = page.getByRole("button", { name: "İşlem ekle" });
  await append.click();
  await expect(page.getByRole("region", { name: "İşlem ayrıntıları" })).toBeVisible();
  await expect(append).toBeFocused();
});

test("akıştaki üçüncü işlem gerçek Composer taslağı ve odağını korur", async ({ page }) => {
  await page.clock.install();
  await open(page, "count=2&composer=1");
  await page.getByText("İşlem 2", { exact: true }).click();
  await page.getByRole("button", { name: "Arka planda işlem ekle" }).click();
  const composer = page.getByRole("textbox", { name: "Mesaj", exact: true });
  await composer.fill("Taslağım");
  await page.clock.runFor(250);
  const panel = page.getByRole("region", { name: "İşlem ayrıntıları" });
  await expect(panel).toBeVisible();
  await expect(composer).toBeFocused();
  await page.keyboard.type(" korunur");
  await expect(composer).toHaveValue("Taslağım korunur");
  await expect(panel.getByText("İşlem 2", { exact: true }).locator("xpath=ancestor::details")).toHaveAttribute("open", "");
});

test("akış sırasında odaktaki satır taşınınca klavye odağı kendi ayrıntısında kalır", async ({ page }) => {
  await page.clock.install();
  await open(page, "count=2");
  await page.getByText("İşlem 2", { exact: true }).click();
  await page.getByRole("button", { name: "Arka planda işlem ekle" }).click();
  await page.getByText("İşlem 2", { exact: true }).locator("xpath=ancestor::summary").focus();
  await page.clock.runFor(250);
  const selected = page.getByRole("region", { name: "İşlem ayrıntıları" }).getByText("İşlem 2", { exact: true });
  await expect(selected.locator("xpath=ancestor::details")).toHaveAttribute("open", "");
  await expect(selected.locator("xpath=ancestor::summary")).toBeFocused();
});

test("kullanıcı isteğiyle panel açma ve kapatma dış taslaktan anlamlı odağa geçer", async ({ page }) => {
  await open(page, "composer=1");
  const composer = page.getByRole("textbox", { name: "Mesaj", exact: true });
  await composer.fill("Dış taslak korunur");
  await page.getByText("İşlem 1", { exact: true }).click();
  const panel = page.getByRole("region", { name: "İşlem ayrıntıları" });
  await expect(panel.getByText("İşlem 1", { exact: true }).locator("xpath=ancestor::summary")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  const preview = page.getByText("İşlem 1", { exact: true }).locator("xpath=ancestor::summary");
  await expect(preview).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "İşlem panelini kapat" }).click();
  await expect(preview).toBeFocused();
  await expect(composer).toHaveValue("Dış taslak korunur");
});
