import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";
for (const theme of ["dark", "light"]) for (const width of [1440, 390, 320]) {
  test(`görsel karşılaştırma ve yerel not ${theme} ${width}`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto(`/e2e/preview.html?state=image&theme=${theme}&inspector=0&sidebar=0`);
    await page.locator(".image-create__open").first().click();
    const dialog = page.getByRole("dialog", { name: "Görsel görüntüleyici" });
    const note = dialog.getByRole("textbox", { name: "Görsel notu" });
    await note.fill("Ön plandaki ışık korunmalı.");
    await note.press("ArrowRight");
    await expect(note).toHaveValue("Ön plandaki ışık korunmalı.");
    await dialog.getByRole("combobox", { name: "Karşılaştırılacak görsel" }).selectOption("/galeri/gorsel-1.png");
    await expect(dialog.getByRole("img", { name: "Karşılaştırılan görsel" })).toBeVisible();
    const stage = await page.locator(".image-create__viewer-stage").boundingBox();
    const side = await page.locator(".image-create__viewer-side").boundingBox();
    expect(stage && side && (stage.x + stage.width <= side.x + 1 || stage.y + stage.height <= side.y + 1)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const path = info.outputPath(`image-review-${theme}-${width}.png`);
    await page.screenshot({ path, animations: "disabled" });
    await info.attach("Görsel karşılaştırma ve yerel not", { path, contentType: "image/png" });
    await note.press("Escape");
    await page.locator(".image-create__open").first().click();
    await expect(dialog.getByRole("textbox", { name: "Görsel notu" })).toHaveValue("Ön plandaki ışık korunmalı.");
  });
}

test("not depolama hatasında viewer kapanışı taslağı silmez ve indirme çalışır", async ({ page }) => {
  await page.addInitScript(() => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      if (key.includes("fusion.image-note.v1")) throw new Error("fixture quota");
      original.call(this, key, value);
    };
  });
  await page.goto('/e2e/preview.html?state=image&theme=dark&inspector=0&sidebar=0');
  await page.locator('.image-create__open').first().click();
  await page.getByRole('textbox', { name: 'Görsel notu' }).fill('Kaybolmaması gereken yerel not.');
  await expect(page.getByRole('alert')).toContainText('kaydedilemedi');
  await page.getByRole('textbox', { name: 'Görsel notu' }).press('Escape');
  await page.locator('.image-create__open').first().click();
  await expect(page.getByRole('textbox', { name: 'Görsel notu' })).toHaveValue('Kaybolmaması gereken yerel not.');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Notu indir' }).click();
  const file = await (await download).path();
  expect(await readFile(file!, 'utf8')).toBe('Kaybolmaması gereken yerel not.');
});
