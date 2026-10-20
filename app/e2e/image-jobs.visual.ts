import { expect, test } from "@playwright/test";

for (const theme of ["dark", "light"] as const) {
  for (const width of [1440, 390, 320]) {
    for (const scenario of ["running", "recovery", "stopping", "error"]) {
      test(`görsel işleri ${scenario} ${theme} ${width}`, async ({ page }, info) => {
        const failures: string[] = [];
        page.on("pageerror", (error) => failures.push(error.message));
        await page.setViewportSize({ width, height: width === 390 ? 844 : width === 320 ? 720 : 960 });
        const mode = scenario === "stopping" ? "running" : scenario;
        await page.goto(`/e2e/preview.html?state=image&theme=${theme}&imageJobs=${mode}&inspector=0&sidebar=0`);
        const jobs = page.getByRole("complementary", { name: "Görsel işleri" });
        await expect(jobs).toBeVisible();
        if (width <= 390) {
          const bounds = await jobs.boundingBox();
          expect(bounds?.height).toBeLessThanOrEqual(180);
          const gallery = await page.getByRole("complementary", { name: "Galeri" }).boundingBox();
          const prompt = await page.locator(".image-create__prompt").boundingBox();
          expect(gallery && prompt && gallery.y + gallery.height <= prompt.y + 1).toBe(true);
          expect(prompt?.height).toBeLessThanOrEqual(140);
          const controls = page.locator(".image-create__prompt-bar select:visible, .image-create__go");
          const boxes = (await Promise.all((await controls.all()).map(item => item.boundingBox()))).filter(Boolean);
          expect(boxes).toHaveLength(3);
          for (const box of boxes) expect(box!.height).toBeGreaterThanOrEqual(40);
          for (let a = 0; a < boxes.length; a++) for (let b = a + 1; b < boxes.length; b++)
            expect(boxes[a]!.x + boxes[a]!.width <= boxes[b]!.x + 1).toBe(true);

        }
        const types = await page.getByRole("tablist", { name: "Üretim türü" }).boundingBox();
        const modes = await page.getByRole("group", { name: "Görsel oluşturma modu" }).boundingBox();
        expect(types && modes && types.x < modes.x + modes.width && modes.x < types.x + types.width
          && types.y < modes.y + modes.height && modes.y < types.y + types.height).toBe(false);
        if (scenario === "error") await expect(jobs.getByRole("button", { name: "İşleri yeniden oku" })).toBeVisible();
        else {
          const stop = jobs.getByRole("button", { name: "Üretimi durdur" });
          await expect(stop).toBeInViewport();
          if (scenario === "stopping") {
            await stop.click();
            await expect(jobs.getByRole("button", { name: "Durduruluyor…" })).toBeDisabled();
          }
        }
        await expect(page.getByRole("button", { name: "Görsel oluştur", exact: true })).toBeDisabled();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
        await page.evaluate(() => document.fonts.ready);
        const path = info.outputPath(`image-jobs-${scenario}-${theme}-${width}.png`);
        await page.screenshot({ path, fullPage: true, animations: "disabled" });
        await info.attach("Görsel iş ekranı", { path, contentType: "image/png" });
        expect(failures).toEqual([]);
      });
    }
  }
}

for (const theme of ["dark", "light"]) {
  test(`mobil iş ayrıntıları ${theme}`, async ({ page }, info) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/e2e/preview.html?state=image&theme=${theme}&imageJobs=recovery&inspector=0&sidebar=0`);
    const details = page.getByRole("button", { name: "İş ayrıntıları" });
    await expect(details).toHaveAttribute("aria-expanded", "false");
    await details.click();
    await expect(details).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByText("Durumu kontrol etmek aynı işi izler, yeni görsel üretmez.", { exact: false })).toBeVisible();
    const path = info.outputPath(`image-jobs-details-${theme}-390.png`);
    await page.screenshot({ path, animations: "disabled" });
    await info.attach("Mobil iş ayrıntıları", { path, contentType: "image/png" });
    await details.click();
    await expect(details).toHaveAttribute("aria-expanded", "false");
  });
}

for (const width of [320, 390]) {
  test(`mobil istem kutusu ve oran seçimi ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/e2e/preview.html?state=image&theme=dark&imageJobs=running&inspector=0&sidebar=0");
    const ratio = page.getByRole("combobox", { name: "Görsel oranı", exact: true });
    await ratio.selectOption("9:16");
    await expect(ratio).toHaveValue("9:16");
    await expect(page.locator('.image-create__ratios [aria-label="9:16"]')).toHaveAttribute("aria-checked", "true");
    const input = page.getByRole("textbox", { name: "Nasıl bir görsel istiyorsun?" });
    await input.fill("Uzun bir görsel tarifi.\n".repeat(20));
    await expect(input).toBeInViewport();
    await expect(page.getByRole("button", { name: "Görsel oluştur", exact: true })).toBeInViewport();
    const box = await page.locator(".image-create__prompt").boundingBox();
    expect(box?.height).toBeLessThanOrEqual(140);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  });
}
