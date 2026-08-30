import { expect, test } from "@playwright/test";

const candidateDir = process.env.FUSION_CANDIDATE_DIR;

const approvedReviewCases = [
  { name: "empty-chat-light-1440x960", query: "state=empty&theme=light&inspector=0", width: 1440, height: 960, anchor: ".empty-state" },
  { name: "empty-chat-dark-1440x960", query: "state=empty&theme=dark&inspector=0", width: 1440, height: 960, anchor: ".empty-state" },
  { name: "conversation-composer-light-1440x960", query: "state=conversation&theme=light", width: 1440, height: 960, anchor: ".composer" },
  { name: "conversation-narrow-light-1024x768", query: "state=conversation&theme=light", width: 1024, height: 768, anchor: ".conversation" },
  { name: "slash-command-menu-m-light-1440x960", query: "state=composer-menu&theme=light", width: 1440, height: 960, anchor: '[role="listbox"][aria-label="Komut önerileri"]' },
  { name: "attachment-chip-light-1440x960", query: "state=composer-attachment&theme=light", width: 1440, height: 960, anchor: '[aria-label="Ekler"]' },
] as const;

for (const theme of ["light", "dark"] as const) {
  test(`sidebar-logo-brand-colors-${theme}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/e2e/preview.html?state=empty&theme=${theme}&inspector=0`);

    const logo = page.locator(".sidebar__brand .fusion-logo");
    await expect(logo).toBeVisible();
    await expect(logo.locator(".fusion-logo__ink")).toHaveCSS(
      "fill",
      theme === "light" ? "rgb(11, 10, 13)" : "rgb(243, 245, 246)",
    );
    await expect(logo.locator(".fusion-logo__signal")).toHaveCSS("fill", "rgb(168, 255, 62)");
  });
}

const cases = [
  { name: "empty-light", query: "state=empty&theme=light&inspector=0", width: 1440, height: 900 },
  { name: "empty-dark", query: "state=empty&theme=dark&inspector=0", width: 1440, height: 900 },
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
  await expect(session.locator(".source-icon")).toBeVisible();
  await expect(session.locator(".sidebar__session-title")).toBeHidden();
  await session.evaluate((button) => {
    button.addEventListener("click", () => {
      document.body.dataset.railKeyboardActivated = "true";
    }, { once: true });
  });
  await session.focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("body")).toHaveAttribute("data-rail-keyboard-activated", "true");
});

for (const fixture of [
  { state: "composer-menu", anchor: '[role="listbox"][aria-label="Komut önerileri"]' },
  { state: "composer-attachment", anchor: '[aria-label="Ekler"]' },
] as const) {
  test(`${fixture.state}-fixture`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.goto(`/e2e/preview.html?state=${fixture.state}&theme=light`);
    await expect(page.locator(fixture.anchor)).toBeVisible();
  });
}

for (const approved of approvedReviewCases) {
  test(`approved-${approved.name}`, async ({ page }) => {
    await page.setViewportSize({ width: approved.width, height: approved.height });
    await page.goto(`/e2e/preview.html?${approved.query}`);
    await expect(page.locator(".app-shell")).toBeVisible();
    await expect(page.locator(approved.anchor)).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect(page).toHaveScreenshot(`${approved.name}.png`, { fullPage: true });
  });
}

for (const candidate of approvedReviewCases) {
  test(`review-candidate-${candidate.name}`, async ({ page }) => {
    test.skip(!candidateDir, "FUSION_CANDIDATE_DIR yalnız inceleme adayı üretirken ayarlanır");
    await page.setViewportSize({ width: candidate.width, height: candidate.height });
    await page.goto(`/e2e/preview.html?${candidate.query}`);
    await expect(page.locator(".app-shell")).toBeVisible();
    await expect(page.locator(candidate.anchor)).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      animations: "disabled",
      path: `${candidateDir}/${candidate.name}.png`,
    });
  });
}
