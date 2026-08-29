import { expect, test } from "@playwright/test";

for (const visualCase of [
  { name: "control-light", state: "control", theme: "light", width: 1440 },
  { name: "control-dark", state: "control", theme: "dark", width: 1440 },
  { name: "control-compact", state: "control", theme: "light", width: 920 },
  { name: "onboarding-light", state: "onboarding", theme: "light", width: 1280 },
  { name: "onboarding-dark", state: "onboarding", theme: "dark", width: 1280 },
  { name: "lessons-light", state: "lessons", theme: "light", width: 1440 },
  { name: "lessons-dark", state: "lessons", theme: "dark", width: 1440 },
  { name: "lessons-compact", state: "lessons", theme: "light", width: 920 },
]) {
  test(visualCase.name, async ({ page }) => {
    await page.setViewportSize({ width: visualCase.width, height: 900 });
    await page.goto(`/e2e/preview.html?state=${visualCase.state}&theme=${visualCase.theme}`);
    const anchor = visualCase.state === "control"
      ? ".control-panel"
      : visualCase.state === "lessons"
        ? ".lessons"
        : ".onboarding";
    await expect(page.locator(anchor)).toBeVisible();
    await expect(page).toHaveScreenshot(`${visualCase.name}.png`, { fullPage: true });
  });
}
