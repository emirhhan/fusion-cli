import { expect, test } from "@playwright/test";

const terminalCases = [
  { name: "terminal-empty", state: "empty" },
  { name: "terminal-active", state: "active" },
  { name: "terminal-ansi-color", state: "ansi" },
  { name: "terminal-closed-error", state: "closed" },
] as const;

for (const terminalCase of terminalCases) {
  test(`terminal-contract-${terminalCase.name}`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`/e2e/preview.html?state=workspace-terminal&terminalState=${terminalCase.state}&theme=light&inspectorWidth=420`);

    await expect(page.getByRole("tab", { name: "Terminal", exact: true })).toBeVisible();
    await expect(page.locator(".terminal-tabs")).toBeVisible();

    if (terminalCase.state === "empty") {
      await expect(page.getByText("Bu çalışma alanında henüz terminal açılmadı.")).toBeVisible();
    } else {
      await page.getByRole("button", { name: "Yeni terminal" }).click();
      await expect(page.getByRole("tab", { name: "Terminal 1" })).toBeVisible();
      await expect(page.locator(".xterm-screen")).toBeVisible();
      if (terminalCase.state === "closed") {
        await expect(page.locator(".xterm-session__status")).toHaveText("Terminal hata ile kapandı (çıkış kodu: 1)");
        await expect(page.locator(".terminal-tabs__dot--hata")).toBeVisible();
      }
    }

    await page.evaluate(() => document.fonts.ready);
    await expect(page).toHaveScreenshot(`${terminalCase.name}.png`, { fullPage: true });
  });
}
