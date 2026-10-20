import {expect, test} from "@playwright/test";

test("history reader can see and use unread jump inside viewport", async ({page}) => {
  await page.setViewportSize({width: 1024, height: 768});
  await page.goto("/e2e/unread.html");
  const scroll = page.locator(".conversation");
  await scroll.evaluate((element) => { element.scrollTo({top: 100, behavior: "instant"}); element.dispatchEvent(new Event("scroll")); });
  await expect.poll(() => scroll.evaluate((element) => element.scrollTop)).toBe(100);
  await page.getByRole("button", {name: "Yanıt ekle"}).click();
  const jump = page.getByRole("button", {name: "Yeni içeriğe git"});
  await expect(jump).toBeInViewport();
  expect(await scroll.evaluate((element) => element.scrollTop)).toBeLessThan(200);
  await jump.click();
  await expect(jump).toHaveCount(0);
  await expect(page.getByText("Yeni cevap", {exact: true})).toBeInViewport();
});
