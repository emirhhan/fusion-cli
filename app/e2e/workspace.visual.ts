import { expect, test } from "@playwright/test";

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
