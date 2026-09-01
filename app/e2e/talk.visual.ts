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
    await expect(panel).toHaveCSS("border-radius", "16px");
    await expect(panel).toHaveCSS("overflow", "hidden");
    const contract = await page.evaluate(() => {
      const panel = document.querySelector<HTMLElement>(".voice-panel")!;
      const title = document.querySelector<HTMLElement>(".voice-panel__title");
      const controls = [...document.querySelectorAll<HTMLElement>(".voice-panel__window-controls button")];
      const interactive = [...document.querySelectorAll<HTMLElement>("button")];
      const panelRect = panel.getBoundingClientRect();
      const titleRect = title?.getBoundingClientRect() ?? null;
      return {
        bodyBackground: getComputedStyle(document.body).backgroundColor,
        controls: controls.map((control) => {
          const rect = control.getBoundingClientRect();
          return { height: rect.height, width: rect.width };
        }),
        cornerIsPanel: document.elementFromPoint(0, 0) === panel,
        interactiveInsideViewport: interactive.every((element) => {
          const rect = element.getBoundingClientRect();
          return rect.left >= 0 && rect.top >= 0 && rect.right <= innerWidth && rect.bottom <= innerHeight;
        }),
        panelRect: { height: panelRect.height, width: panelRect.width },
        rootBackground: getComputedStyle(document.documentElement).backgroundColor,
        titleCenterOffset: titleRect ? Math.abs(titleRect.left + titleRect.width / 2 - innerWidth / 2) : 0,
      };
    });
    expect(contract.bodyBackground).toBe("rgba(0, 0, 0, 0)");
    expect(contract.rootBackground).toBe("rgba(0, 0, 0, 0)");
    expect(contract.cornerIsPanel).toBe(false);
    expect(contract.panelRect).toEqual({ width: visual.width, height: visual.height });
    expect(contract.interactiveInsideViewport).toBe(true);
    for (const control of contract.controls) expect(control).toEqual({ width: 12, height: 12 });
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
