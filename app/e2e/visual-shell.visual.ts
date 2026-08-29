import { expect, test } from "@playwright/test";

const cases = [
  { name: "empty-light", query: "state=empty&theme=light&inspector=0", width: 1440, height: 900 },
  { name: "conversation-light", query: "state=conversation&theme=light", width: 1440, height: 900 },
  { name: "conversation-dark", query: "state=conversation&theme=dark", width: 1440, height: 900 },
  { name: "conversation-medium", query: "state=conversation&theme=light", width: 1100, height: 820 },
  { name: "conversation-compact", query: "state=conversation&theme=light", width: 820, height: 760 },
  { name: "approval-light", query: "state=approval&theme=light", width: 1440, height: 900 },
] as const;

for (const visualCase of cases) {
  test(visualCase.name, async ({ page }) => {
    await page.setViewportSize({ width: visualCase.width, height: visualCase.height });
    await page.goto(`/e2e/preview.html?${visualCase.query}`);
    await expect(page.locator(".app-shell")).toBeVisible();
    await expect(page).toHaveScreenshot(`${visualCase.name}.png`, { fullPage: true });
  });
}

test("keyboard-focus", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/e2e/preview.html?state=empty&theme=light");
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus-visible")).toBeVisible();
  await expect(page).toHaveScreenshot("keyboard-focus.png", { fullPage: true });
});

test("compact-rail-keyboard-activation", async ({ page }) => {
  await page.setViewportSize({ width: 820, height: 760 });
  await page.goto("/e2e/preview.html?state=conversation&theme=light&inspector=0");
  const session = page.getByRole("button", { name: "macOS uygulaması" });
  await expect(session).toBeVisible();
  const identityColors = await session.locator(".sidebar__session-title").evaluate((label) => ({
    full: getComputedStyle(label).color,
    initial: getComputedStyle(label, "::first-letter").color,
  }));
  expect(identityColors.full).toBe("rgba(0, 0, 0, 0)");
  expect(identityColors.initial).not.toBe(identityColors.full);
  await session.evaluate((button) => {
    button.addEventListener("click", () => {
      document.body.dataset.railKeyboardActivated = "true";
    }, { once: true });
  });
  await session.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("body")).toHaveAttribute("data-rail-keyboard-activated", "true");
});
