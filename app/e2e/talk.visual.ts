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
    await expect(page.getByRole("region", { name: "Fusion Talk" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Fusion Talk" })).toHaveCSS("border-radius", "0px");
    await expect(page.getByRole("region", { name: "Fusion Talk" })).toHaveCSS("box-shadow", "none");
    if (visual.query.includes("voiceMode=mini") && visual.query.includes("voice-listening")) {
      const microphone = page.getByRole("button", { name: "Dinlemeyi durdur" });
      await expect(microphone).toBeVisible();
      const box = await microphone.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(visual.width);
    }
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
