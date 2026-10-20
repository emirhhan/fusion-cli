import { expect, test } from "@playwright/test";

for (const visualCase of [
  { name: "capabilities-light", theme: "light", width: 1440 },
  { name: "capabilities-dark", theme: "dark", width: 1440 },
  { name: "capabilities-compact", theme: "light", width: 920 },
]) {
  test(visualCase.name, async ({ page }) => {
    await page.setViewportSize({ width: visualCase.width, height: 900 });
    await page.goto(`/e2e/preview.html?state=capabilities&theme=${visualCase.theme}`);
    await expect(page.getByText("frontend-design")).toBeVisible();
    if (visualCase.width > 1000) {
      await page.getByRole("button", { name: "frontend-design ayrıntılarını aç" }).click();
      await expect(page.getByText(/Bu uzmanlık/)).toBeVisible();
    }
    await expect(page).toHaveScreenshot(`${visualCase.name}.png`, { fullPage: true });
  });
}
