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
  await page.getByRole("tab", { name: "Terminal", exact: true }).click();
  await page.getByRole("button", { name: "Yeni terminal" }).click();
  await expect(page.locator(".xterm-session__status")).toHaveText("Terminal hata ile kapandı (çıkış kodu: 1)");
  await expect(page).toHaveScreenshot("workspace-terminal-error.png", { fullPage: true });
});

test("workspace-tests-compact", async ({ page }) => {
  await open(page, "workspace-ready", "light", 920);
  await page.getByRole("tab", { name: "Testler" }).click();
  await expect(page.getByRole("region", { name: "Doğrulama kanıtları" })).toBeVisible();
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

test("workspace-web-preview", async ({ page }) => {
  await open(page);
  await page.getByRole("tab", { name: "Önizleme" }).click();
  await page.getByRole("tab", { name: "Web" }).click();
  await page.getByRole("textbox", { name: "Yerel önizleme adresi" }).fill("http://127.0.0.1:4174/e2e/local-preview.html");
  await page.getByRole("button", { name: "Adrese git" }).click();
  await expect(page.getByTitle("Yerel geliştirme önizlemesi")).toBeVisible();
  await expect(page).toHaveScreenshot("workspace-web-preview.png", { fullPage: true });
});

test("workspace-inspector-collapsed", async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 760 });
  await page.goto("/e2e/preview.html?state=workspace-ready&theme=light&inspectorLayout=collapsed");
  await expect(page.getByRole("button", { name: "Çalışma panelini genişlet" })).toBeVisible();
  await expect(page).toHaveScreenshot("workspace-inspector-collapsed.png", { fullPage: true });
});

for (const candidate of [
  { name: "inspector-terminal-normal-1440x900", query: "state=workspace-error&theme=light&inspectorWidth=420", anchor: ".terminal-tabs__panel", openComposer: false },
  { name: "inspector-terminal-command-1440x900", query: "state=workspace-error&theme=light&inspectorWidth=420", anchor: '[aria-label="Terminal komutu"]', openComposer: true },
  { name: "inspector-preview-web-1440x900", query: "state=workspace-ready&theme=light&inspectorWidth=520&inspectorTab=preview", anchor: "#local-preview-url", openComposer: false, previewUrl: "http://127.0.0.1:4174/e2e/local-preview.html" },
  { name: "inspector-collapsed-1440x900", query: "state=workspace-ready&theme=light&inspectorLayout=collapsed", anchor: '[aria-label="Çalışma panelini genişlet"]', openComposer: false },
] as const) {
  test(`review-candidate-${candidate.name}`, async ({ page }) => {
    test.skip(!workspaceCandidateDir, "FUSION_WORKSPACE_CANDIDATE_DIR yalnız inceleme adayı üretirken verilir");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/e2e/preview.html?${candidate.query}`);
    if (candidate.openComposer) await page.getByRole("button", { name: "Yeni terminal" }).click();
    if ("previewUrl" in candidate) {
      await page.locator("#local-preview-url").fill(candidate.previewUrl);
      await page.getByRole("button", { name: "Adrese git" }).click();
      await expect(page.getByTitle("Yerel geliştirme önizlemesi")).toBeVisible();
    }
    await expect(page.locator(candidate.anchor)).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({
      animations: "disabled",
      path: `${workspaceCandidateDir}/${candidate.name}.png`,
    });
  });
}
