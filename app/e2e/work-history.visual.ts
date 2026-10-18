import { test, expect } from "@playwright/test";
for (const theme of ["dark", "light"]) for (const width of [390, 1440]) {
 test(`Codex akışı ${theme} ${width}`, async ({page},info)=>{
  await page.setViewportSize({width,height:900});
  await page.goto(`/e2e/work-history.html?theme=${theme}`);
  await expect(page.locator(".conversation__work-details")).toHaveCount(0);
  await expect(page.getByText("Review resume çalışmayı bitirdi")).toBeVisible();
  await page.locator(".conversation").evaluate(el=>{el.scrollTop=0;});
  await page.screenshot({path:info.outputPath("codex-akis.png"),animations:"disabled"});
  const card=page.getByRole("region",{name:"Dosya değişiklikleri"});
  await card.scrollIntoViewIfNeeded();
  await expect(card).toContainText("10 dosya düzenlendi");
  await expect(card.getByRole("button",{name:"7 dosya daha göster"})).toBeVisible();
  expect(await page.locator("body").evaluate(el=>el.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:info.outputPath("codex-sonuc.png"),animations:"disabled"});
  const view=card.getByRole("button",{name:"Değişiklikleri görüntüle"});
  await view.focus();await page.keyboard.press("Enter");
  await expect(view).toHaveAttribute("aria-expanded","true");
  await expect(card.locator(".diff-card")).toHaveCount(10);
  await card.getByRole("button",{name:"7 dosya daha göster"}).click();
  await card.getByRole("button",{name:"tests/test_turn_journal.py dosyasını aç",exact:true}).first().click();
  await expect(page.locator("html")).toHaveAttribute("data-opened-file","tests/test_turn_journal.py");
  await page.goto(`/e2e/work-history.html?theme=${theme}&running=1`);
  await expect(page.getByRole("region",{name:"Dosya değişiklikleri"})).toHaveCount(0);
 });
}
