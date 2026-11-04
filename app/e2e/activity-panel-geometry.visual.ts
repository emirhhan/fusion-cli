import { expect, test, type Page } from "@playwright/test";

async function bounds(page: Page) {
  return page.getByRole("region", { name: "İşlem ayrıntıları" }).evaluate(panel => {
    const viewport = document.querySelector(".conversation")!;
    const read = (node: Element) => { const r = node.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height }; };
    return { panel: read(panel), viewport: read(viewport), outerTop: viewport.scrollTop };
  });
}
async function expectContained(page: Page) {
  const measured = await bounds(page);
  expect(measured.panel.top).toBeGreaterThanOrEqual(measured.viewport.top - 1);
  expect(measured.panel.bottom).toBeLessThanOrEqual(measured.viewport.bottom + 1);
  expect(measured.panel.left).toBeGreaterThanOrEqual(measured.viewport.left - 1);
  expect(measured.panel.right).toBeLessThanOrEqual(measured.viewport.right + 1);
}

test("uzun istemden açılan panel gerçek sohbet görünümüne sığar; son kod içten kaydırılır", async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 900 });
  await page.goto("/e2e/preview.html?state=activity-panel&tail=0&composer=1&longPrompt=1");
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page.getByText("Sonuç hazır.", { exact: true })).toBeVisible();
  const before = await page.locator(".conversation").evaluate(node => node.scrollTop);
  await page.getByText("İşlem 1", { exact: true }).click();
  const panel = page.getByRole("region", { name: "İşlem ayrıntıları" });
  console.log(JSON.stringify({ stage: "long-prompt-open", before, ...await bounds(page) }));
  await expectContained(page);
  expect((await bounds(page)).outerTop).toBe(before);
  const inner = panel.locator(".work-activity-panel__scroll");
  await inner.hover({ position: { x: 1, y: 100 } });
  await page.mouse.wheel(0, 5000);
  await expect.poll(() => inner.evaluate(node => node.scrollTop)).toBeGreaterThan(0);
  const last = panel.getByText("İşlem 14", { exact: true });
  const lastBounds = await last.evaluate(node => node.getBoundingClientRect().bottom);
  expect(lastBounds).toBeLessThanOrEqual((await inner.boundingBox())!.y + (await inner.boundingBox())!.height);
  await last.click();
  await inner.hover({ position: { x: 1, y: 100 } });
  await page.mouse.wheel(0, 5000);
  await expect.poll(() => inner.evaluate(node => node.scrollTop + node.clientHeight >= node.scrollHeight - 1)).toBe(true);
  const output = last.locator("xpath=ancestor::details").locator(".activity__trail-output");
  const outputBounds = await output.boundingBox();
  const innerBounds = (await inner.boundingBox())!;
  await page.mouse.move(innerBounds.x + 50, Math.max(outputBounds!.y, innerBounds.y) + 30);
  await page.mouse.wheel(0, 5000);
  await expect.poll(() => output.evaluate(node => node.scrollTop + node.clientHeight >= node.scrollHeight - 1)).toBe(true);
  expect((await bounds(page)).outerTop).toBe(before);
  await expectContained(page);
  await page.setViewportSize({ width: 430, height: 650 });
  await expect.poll(async () => { const r = await bounds(page); return r.panel.bottom <= r.viewport.bottom + 1 && r.panel.top >= r.viewport.top - 1; }).toBe(true);
  await expectContained(page);
  expect(await inner.evaluate(node => node.clientHeight)).toBeGreaterThan(0);
  await page.getByRole("button", { name: "Sohbet değiştir" }).click();
  await expect(panel).toHaveCount(0);
});
