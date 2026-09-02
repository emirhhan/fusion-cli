import { expect, test } from "@playwright/test";

const candidateDir = process.env.FUSION_CANDIDATE_DIR;

const cases = [
  { name: "talk-normal-listening-light", query: "state=voice-listening&theme=light", width: 380, height: 460 },
  { name: "talk-normal-talking-dark", query: "state=voice-talking&theme=dark", width: 380, height: 460 },
  { name: "talk-mini-listening-light", query: "state=voice-listening&voiceMode=mini&theme=light", width: 360, height: 112 },
  { name: "talk-mini-approval-dark", query: "state=voice-approval&voiceMode=mini&theme=dark", width: 360, height: 112 },
] as const;

for (const visual of cases) {
  test(`talk-contract-${visual.name}`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: visual.width, height: visual.height });
    await page.goto(`/e2e/preview.html?${visual.query}`);
    const panel = page.getByRole("region", { name: "Fusion Talk" });
    await expect(panel).toBeVisible();
    await expect(page.locator("body")).toHaveAttribute("data-talk-surface", "true");
    await expect(page.locator("body")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(page.locator("html")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(panel).toHaveCSS("border-radius", "16px");
    await expect(panel).toHaveCSS("overflow", "hidden");
    const contract = await page.evaluate(() => {
      const panel = document.querySelector<HTMLElement>(".voice-panel")!;
      const title = document.querySelector<HTMLElement>(".voice-panel__title");
      const controls = [...document.querySelectorAll<HTMLElement>(".voice-panel__window-controls button")];
      const avatar = document.querySelector<HTMLElement>(".fusion-avatar");
      const microphone = document.querySelector<HTMLElement>(".voice-panel__mic");
      const settingsProbe = document.createElement("button");
      settingsProbe.className = "voice-panel__settings-toggle";
      panel.append(settingsProbe);
      const settingsBorderWidth = getComputedStyle(settingsProbe).borderWidth;
      settingsProbe.remove();
      const interactive = [...document.querySelectorAll<HTMLElement>("button")];
      const panelRect = panel.getBoundingClientRect();
      const titleRect = title?.getBoundingClientRect() ?? null;
      return {
        bodyBackground: getComputedStyle(document.body).backgroundColor,
        controls: controls.map((control) => {
          const rect = control.getBoundingClientRect();
          const style = getComputedStyle(control);
          return { background: style.backgroundColor, boxShadow: style.boxShadow, height: rect.height, left: rect.left, top: rect.top, width: rect.width };
        }),
        glyphOpacity: controls.map((control) => getComputedStyle(control.querySelector<HTMLElement>(".voice-panel__traffic-glyph")!).opacity),
        cornerIsPanel: document.elementFromPoint(0, 0) === panel,
        interactiveInsideViewport: interactive.every((element) => {
          const rect = element.getBoundingClientRect();
          return rect.left >= 0 && rect.top >= 0 && rect.right <= innerWidth && rect.bottom <= innerHeight;
        }),
        panelRect: { height: panelRect.height, width: panelRect.width },
        miniTitleBarClearance: avatar && microphone
          ? Math.min(avatar.getBoundingClientRect().top, microphone.getBoundingClientRect().top) - Math.max(...controls.map((control) => control.getBoundingClientRect().bottom))
          : null,
        rootBackground: getComputedStyle(document.documentElement).backgroundColor,
        settingsBorderWidth,
        titleCenterOffset: titleRect ? Math.abs(titleRect.left + titleRect.width / 2 - innerWidth / 2) : 0,
      };
    });
    expect(contract.bodyBackground).toBe("rgba(0, 0, 0, 0)");
    expect(contract.rootBackground).toBe("rgba(0, 0, 0, 0)");
    expect(contract.cornerIsPanel).toBe(false);
    expect(contract.panelRect).toEqual({ width: visual.width, height: visual.height });
    expect(contract.interactiveInsideViewport).toBe(true);
    for (const control of contract.controls) {
      expect(control.width).toBe(12);
      expect(control.height).toBe(12);
      expect(control.boxShadow).toContain("inset");
    }
    expect(contract.controls.map((control) => control.background)).toEqual([
      "rgb(255, 95, 87)",
      "rgb(254, 188, 46)",
      "rgb(40, 200, 64)",
    ]);
    expect(contract.controls.slice(1).map((control, index) => control.left - contract.controls[index].left)).toEqual([20, 20]);
    expect(contract.controls[0].left).toBe(visual.query.includes("voiceMode=mini") ? 14 : 16);
    expect(contract.controls[0].top).toBeGreaterThanOrEqual(14);
    expect(contract.controls[0].top).toBeLessThanOrEqual(16);
    expect(contract.glyphOpacity).toEqual(["0", "0", "0"]);
    if (visual.query.includes("voiceMode=mini")) expect(contract.miniTitleBarClearance).toBeGreaterThanOrEqual(8);
    if (!visual.query.includes("voiceMode=mini")) expect(contract.settingsBorderWidth).toBe("0px");
    if (!visual.query.includes("voiceMode=mini")) expect(contract.titleCenterOffset).toBeLessThanOrEqual(1);
    const microphone = page.getByRole("button", { name: /Dinlemeyi durdur|Konuşmaya başla/ });
    await expect(microphone).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await expect(page).toHaveScreenshot(`${visual.name}.png`, { fullPage: true });
  });

  test(`talk-candidate-${visual.name}`, async ({ page }) => {
    test.skip(!candidateDir, "Yalnız kullanıcı görsel incelemesi için çalışır");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: visual.width, height: visual.height });
    await page.goto(`/e2e/preview.html?${visual.query}`);
    await expect(page.getByRole("region", { name: "Fusion Talk" })).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ animations: "disabled", path: `${candidateDir}/${visual.name}.png` });
  });
}

test("talk-traffic-glyphs-reveal-only-on-native-hover-or-keyboard-focus", async ({ page }) => {
  await page.setViewportSize({ width: 380, height: 460 });
  await page.goto("/e2e/preview.html?state=voice-listening&theme=light");
  const controls = page.getByLabel("Pencere denetimleri");
  const buttons = controls.getByRole("button");
  const glyphs = controls.locator(".voice-panel__traffic-glyph");

  await expect(glyphs).toHaveCount(3);
  for (const glyph of await glyphs.all()) await expect(glyph).toHaveCSS("opacity", "0");

  await buttons.first().hover();
  for (const glyph of await glyphs.all()) await expect(glyph).toHaveCSS("opacity", "1");

  await page.mouse.move(200, 200);
  await buttons.nth(1).focus();
  await expect(glyphs.nth(0)).toHaveCSS("opacity", "0");
  await expect(glyphs.nth(1)).toHaveCSS("opacity", "1");
  await expect(glyphs.nth(2)).toHaveCSS("opacity", "0");
});

test("talk-mini-error-keeps-retry-microphone-visible", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 112 });
  await page.goto("/e2e/preview.html?state=voice-error&voiceMode=mini&theme=light");
  const microphone = page.getByRole("button", { name: "Konuşmaya başla" });
  await expect(microphone).toBeVisible();
  const box = await microphone.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(360);
});
