import { expect, test } from "@playwright/test";

const cases = [
  { name: "history-source", state: "history-source", width: 1440, height: 900 },
  { name: "history-preview", state: "history-preview", width: 1440, height: 900 },
  { name: "history-empty", state: "history-empty", width: 1180, height: 820 },
  { name: "history-error", state: "history-error", width: 1180, height: 820 },
  { name: "history-long", state: "history-long", width: 920, height: 760 },
] as const;

for (const visualCase of cases) {
  test(visualCase.name, async ({ page }) => {
    await page.setViewportSize({ width: visualCase.width, height: visualCase.height });
    await page.goto(`/e2e/preview.html?state=${visualCase.state}&theme=light`);
    await expect(page.getByRole("dialog", { name: "Bir konuşma seçin" })).toBeVisible();
    await expect(page).toHaveScreenshot(`${visualCase.name}.png`, { fullPage: true });
  });
}

test("history-warning", async ({ page }) => {
  await page.setViewportSize({ width: 1180, height: 820 });
  await page.goto("/e2e/preview.html?state=history-warning&theme=dark");
  await page.getByRole("button", { name: "Bu konuşmayı devral" }).click();
  await expect(page.getByText(/2 hassas değer/i)).toBeVisible();
  await expect(page).toHaveScreenshot("history-warning.png", { fullPage: true });
});
