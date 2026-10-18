import { test, expect } from "@playwright/test";

for (const theme of ["dark", "light"]) for (const width of [390, 1440]) {
  test(`ara anlatım ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 800 });
    await page.goto(`/e2e/work-history.html?theme=${theme}`);
    const details = page.locator(".conversation__work-details");
    await expect(details).toHaveCount(1);
    await expect(details).not.toHaveAttribute("open", "");
    await expect(page.getByText("İş durduruldu.", { exact: false })).toBeVisible();
    await expect(details.locator("ol").first()).not.toBeVisible();
    expect(await page.locator("body").evaluate((el) => el.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath("kapali.png"), animations: "disabled" });
    await details.locator("summary").first().focus();
    await page.keyboard.press("Enter");
    await expect(details).toHaveAttribute("open", "");
    await expect(details.getByText("Adım 24:", { exact: false })).toBeVisible();
    await page.keyboard.press("Enter");
    await expect(details).not.toHaveAttribute("open", "");
    await page.goto(`/e2e/work-history.html?theme=${theme}&running=1`);
    await expect(page.locator(".conversation__work-current")).toContainText("Adım 24");
    await expect(page.locator(".conversation__work-details > ol")).not.toBeVisible();
  });
}
