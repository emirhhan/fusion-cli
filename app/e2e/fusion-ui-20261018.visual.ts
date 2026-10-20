import { expect, test } from "@playwright/test";

for (const theme of ["light", "dark"] as const) {
  for (const width of [1440, 900]) {
    test(`Kits parity and rail account ${theme} ${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.addInitScript(() => { document.addEventListener("DOMContentLoaded", () => { document.documentElement.dataset.fusionTitlebarInset = "true"; }); });
      await page.goto(`/e2e/preview.html?state=empty&theme=${theme}&rail=home&inspector=0`);
      const rail = page.locator(".main-rail");
      await expect(rail).toHaveCSS("width", "52px");
      const titlebar = page.locator(".app-frame__titlebar");
      const topBox = await titlebar.boundingBox();
      const railBox = await rail.boundingBox();
      expect(topBox).toMatchObject({ x: 0, y: 0, width, height: 40 });
      expect(railBox!.y).toBe(40);
      await expect(titlebar).toHaveCSS("background-color", await rail.evaluate(el => getComputedStyle(el).backgroundColor));
      await expect(page.locator(".app-frame > .app-shell")).toHaveCSS("border-top-left-radius", "14px");
      expect((await page.locator(".app-header__nav").boundingBox())!.x).toBeGreaterThanOrEqual(72);
      await expect(rail).toHaveCSS("background-color", theme === "dark" ? "rgb(24, 24, 24)" : "rgb(237, 237, 237)");
      await expect(page.locator(".app-shell__sidebar")).toHaveCSS("background-color", theme === "dark" ? "rgb(38, 38, 38)" : "rgb(249, 249, 249)");
      const home = page.getByRole("button", { name: "Home", exact: true });
      const tooltip = home.getByRole("tooltip");
      await expect(tooltip).toBeHidden();
      await home.hover();
      await expect(tooltip).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(tooltip).toBeHidden();
      await page.mouse.move(600, 400);
      await home.hover();
      await tooltip.hover();
      await expect(tooltip).toBeVisible();
      await home.focus();
      await page.keyboard.press("Escape");
      await expect(tooltip).toBeHidden();
      const account = page.getByRole("button", { name: "Hesap menüsü" });
      await expect(rail.getByRole("button", { name: "Hesap menüsü" })).toBeVisible();
      expect(await page.locator(".sidebar .sidebar__profile-trigger").count()).toBe(0);
      const accountBox = await account.boundingBox();
      expect(accountBox!.x).toBeLessThan(52);
      expect(accountBox!.y).toBeGreaterThan(700);
      await account.click();
      const menu = page.getByRole("menu", { name: "Profil menüsü" });
      await expect(menu).toBeVisible();
      const box = await menu.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      expect(box!.y + box!.height).toBeLessThanOrEqual(800);
      await page.keyboard.press("Escape");
      await expect(menu).toBeHidden();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (width === 1440) await page.screenshot({ path: `/tmp/fusion-v3-frame-${theme}.png` });
    });
  }
}

test("project groups, hover information, response actions and bounded composer", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.addInitScript(() => {
    Object.defineProperty(window, "__TAURI_INTERNALS__", { value: {
      convertFileSrc: (path: string) => `/guide/${Number(path.match(/\d+/)?.[0] ?? 0) % 2 ? "kits-menu" : "ekip"}.webp`,
    } });
  });
  await page.goto("/e2e/preview.html?state=composer-attachment&long=1&projects=1&theme=dark&rail=home&inspector=0&fullComposer=1");
  const desktop = page.getByRole("region", { name: "Desktop", exact: true });
  await expect(desktop.locator(".sidebar__session")).toHaveCount(5);
  await page.getByRole("button", { name: "Desktop: Daha fazla göster" }).click();
  await expect(desktop.locator(".sidebar__session")).toHaveCount(7);
  const project = page.getByRole("button", { name: "02-example projesini aç", exact: true });
  await project.click();
  await expect(project).toHaveAttribute("aria-expanded", "false");
  await project.hover();
  await expect(page.getByRole("dialog", { name: "02-example proje bilgileri" })).toBeVisible();
  await page.screenshot({ path: "/tmp/fusion-v2-project-info.png" });
  await page.keyboard.press("Escape");
  const text = page.getByRole("textbox", { name: "Mesaj" });
  expect(await text.evaluate(el => el.scrollHeight > el.clientHeight)).toBe(true);
  const images = page.locator('.composer__attachment[data-gorsel="true"]');
  await expect(images).toHaveCount(7);
  const attachments = page.getByLabel("Ekler", { exact: true });
  expect(await attachments.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true);
  await expect(page.getByRole("button", { name: "Gönder", exact: true })).toBeInViewport();
  await expect(page.getByRole("button", { name: "Yeni sohbette devam et", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/fusion-v2-long-composer.png" });
});

test("inspector overlay starts directly below shared titlebar", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 800 });
  await page.goto("/e2e/preview.html?state=conversation&theme=dark&rail=home&inspector=1");
  await expect(page.locator(".app-shell__inspector")).toHaveCSS("top", "40px");
  await expect(page.locator(".app-shell__backdrop")).toHaveCSS("top", "40px");
});
