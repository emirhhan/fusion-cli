import { test, expect } from "@playwright/test";
for (const theme of ["dark", "light"]) for (const width of [1440, 390, 320]) {
  test(`kurulum sağlayıcı kaydırma ve gezinme ${theme} ${width}`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width, height: width > 500 ? 833 : 640 });
    await page.goto(`/e2e/onboarding-flow.html?theme=${theme}`);
    await page.getByRole("button", { name: "Bağlan", exact: true }).first().click();
    const next = page.getByRole("button", { name: "Devam et", exact: true });
    await expect(next).toBeVisible();
    const footer = page.getByRole("contentinfo");
    const bounds = await footer.boundingBox();
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(page.viewportSize()!.height + 1);
    const font = await page.getByRole("button", { name: "Anahtarı sına", exact: true }).evaluate(el => getComputedStyle(el).fontFamily);
    expect(font).toContain("Inter");
    const panel = page.locator(".control-panel");
    expect(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await panel.evaluate(el => { el.scrollTop = el.scrollHeight; });
    expect(await panel.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
    await expect(next).toBeVisible();
    await panel.evaluate(el => { el.scrollTop = 0; });
    await page.getByLabel("API anahtarı", { exact: true }).fill("SYNTHETIC_BROWSER_KEY");
    await expect(next).toBeDisabled();
    await page.getByRole("button", { name: "Kaydet", exact: true }).click();
    await expect(next).toBeEnabled();
    await expect(page.getByText("OpenAI anahtarı kaydedildi.", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const shot = info.outputPath(`onboarding-provider-${theme}-${width}.png`);
    await page.screenshot({ path: shot, animations: "disabled" });
    await info.attach("Kurulum sağlayıcı formu · sentetik taşıma", { path: shot, contentType: "image/png" });
    await next.click();
    await expect(page.getByRole("heading", { name: "Bir örnek proje seçin" })).toBeVisible();
    await page.getByRole("button", { name: "Proje seçmeden devam et", exact: true }).click();
    await expect(page.getByText("Test kurulumu tamamlandı", { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });
}
test("sağlayıcı formundan atlama yolu görünür", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/e2e/onboarding-flow.html?theme=dark");
  await page.getByRole("button", { name: "Bağlan", exact: true }).first().click();
  await page.getByRole("button", { name: "Şimdilik atla", exact: true }).click();
  await expect(page.getByText("Test kurulumu tamamlandı", { exact: true })).toBeVisible();
});

test("boş geçmiş kurulum hatası değildir ve kaynak adımı atlanır", async ({ page }, info) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/e2e/onboarding-flow.html?theme=dark&step=sources");
  await expect(page.getByRole("heading", { name: "İçe aktarılacak sohbet bulunamadı" })).toBeVisible();
  await expect(page.locator(".onboarding__brand-mark img.fusion-logo")).toBeVisible();
  const skip = page.getByRole("button", { name: "Şimdilik atla", exact: true });
  await expect(skip).toBeInViewport();
  const shot = info.outputPath("onboarding-sources-dark-320.png");
  await page.screenshot({ path: shot, animations: "disabled" });
  await info.attach("Boş kaynak · sentetik taşıma", { path: shot, contentType: "image/png" });
  await skip.click();
  await expect(page.getByText("Test kurulumu tamamlandı", { exact: true })).toBeVisible();
});
