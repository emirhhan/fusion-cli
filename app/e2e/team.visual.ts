import { expect, test } from "@playwright/test";

/** Ekip kartları: paralel alt ajanlar yan yana, dar ekranda alt alta; iki tema. */
const cases = [
  { name: "team-1440-light", query: "state=team&inspector=0&theme=light", width: 1440, height: 900 },
  { name: "team-1440-dark", query: "state=team&inspector=0&theme=dark", width: 1440, height: 900 },
  { name: "team-375-light", query: "state=team&inspector=0&theme=light", width: 375, height: 812 },
] as const;

for (const visual of cases) {
  test(`team-${visual.name}`, async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.setViewportSize({ width: visual.width, height: visual.height });
    await page.goto(`/e2e/preview.html?${visual.query}`);
    const ekip = page.getByRole("region", { name: "3 ajan aynı anda çalışıyor" });
    await expect(ekip).toBeVisible();
    await expect(page.getByRole("img", { name: "Görsel Üretici" })).toBeVisible();
    const tasma = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(tasma).toBe(0);
    await expect(ekip).toHaveScreenshot(`${visual.name}.png`, {
      // Süre sayacı her koşuda farklıdır; görüntü karşılaştırmasına girmez.
      mask: [page.locator(".agent-card__state")],
    });
  });
}
