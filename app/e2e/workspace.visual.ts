import { expect, test } from "@playwright/test";

const workspaceCandidateDir = process.env.FUSION_WORKSPACE_CANDIDATE_DIR;

async function open(page: import("@playwright/test").Page, state = "workspace-ready", theme = "light", width = 1440) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`/e2e/preview.html?state=${state}&theme=${theme}`);
  await expect(page.getByRole("tab", { name: "Dosyalar" })).toBeVisible();
}

test("workspace-files-long", async ({ page }) => {
  await open(page);
  await page.getByRole("treeitem", { name: "README.md" }).click();
  await expect(page.getByText("Profesyonel macOS çalışma alanı")).toBeVisible();
  await expect(page).toHaveScreenshot("workspace-files-long.png", { fullPage: true });
});

test("workspace-diff-dark", async ({ page }) => {
  await open(page, "workspace-ready", "dark");
  await page.getByRole("tab", { name: "Değişiklikler" }).click();
  await expect(page.getByText("+print('Fusion hazır')")).toBeVisible();
  await expect(page).toHaveScreenshot("workspace-diff-dark.png", { fullPage: true });
});

test("workspace-terminal-error", async ({ page }) => {
  await open(page, "workspace-error");
  await page.getByRole("tab", { name: "Terminal" }).click();
  await expect(page.getByText("FAIL src/App.test.tsx")).toBeVisible();
  await expect(page).toHaveScreenshot("workspace-terminal-error.png", { fullPage: true });
});

test("workspace-tests-compact", async ({ page }) => {
  await open(page, "workspace-ready", "light", 920);
  await page.getByRole("tab", { name: "Testler" }).click();
  await expect(page.getByText("100 tests passed")).toBeVisible();
  await expect(page).toHaveScreenshot("workspace-tests-compact.png", { fullPage: true });
});

test("workspace-image-preview", async ({ page }) => {
  await open(page);
  await page.getByRole("treeitem", { name: "assets" }).click();
  await page.getByRole("treeitem", { name: "fusion-preview.svg" }).click();
  await page.getByRole("tab", { name: "Önizleme" }).click();
  await expect(page.getByRole("img", { name: "assets/fusion-preview.svg önizlemesi" })).toBeVisible();
  await expect(page).toHaveScreenshot("workspace-image-preview.png", { fullPage: true });
});

for (const candidate of [
  { name: "inspector-terminal-normal-1440x900", query: "state=workspace-error&theme=light&inspectorWidth=420", anchor: ".terminal-panel" },
  { name: "inspector-collapsed-1440x900", query: "state=workspace-ready&theme=light&inspectorLayout=collapsed", anchor: '[aria-label="Çalışma panelini genişlet"]' },
] as const) {
  test(`review-candidate-${candidate.name}`, async ({ page }) => {
    test.skip(!workspaceCandidateDir, "FUSION_WORKSPACE_CANDIDATE_DIR yalnız inceleme adayı üretirken verilir");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/e2e/preview.html?${candidate.query}`);
    await expect(page.locator(candidate.anchor)).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      animations: "disabled",
      path: `${workspaceCandidateDir}/${candidate.name}.png`,
    });
  });
}
