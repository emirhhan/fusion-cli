import { expect, test, type Page } from "@playwright/test";

const proseSelector = ".conversation__message--assistant .markdown";
const answerSelector = `${proseSelector}:has(h1)`;

async function openTypography(page: Page, theme = "light") {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto(`/e2e/preview.html?state=typography&theme=${theme}&inspector=0&sidebar=0`);
  await expect(page.locator(`${answerSelector} h1`)).toBeVisible();
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page.locator(".skip-links")).toHaveCSS("position", "fixed");
  await page.locator(".conversation").evaluate(node => {
    (node as HTMLElement).style.scrollBehavior = "auto";
    node.scrollTop = 0;
    node.dispatchEvent(new Event("scroll"));
  });
  await expect.poll(() => page.locator(".conversation").evaluate(node => node.scrollTop)).toBe(0);
}

async function platformFonts(page: Page, selector: string) {
  const cdp = await page.context().newCDPSession(page);
  try {
    await cdp.send("DOM.enable"); await cdp.send("CSS.enable");
    const { root } = await cdp.send("DOM.getDocument");
    const { nodeId } = await cdp.send("DOM.querySelector", { nodeId: root.nodeId, selector });
    const { fonts } = await cdp.send("CSS.getPlatformFontsForNode", { nodeId });
    return fonts as { familyName: string; postScriptName: string; isCustomFont: boolean; glyphCount: number }[];
  } finally { await cdp.detach(); }
}

test("asistan yerel Inter ile çizilir; kullanıcı ve kontroller korunur", async ({ page }) => {
  await openTypography(page);
  for (const selector of [`${answerSelector} > p`, `${answerSelector} em`, `${answerSelector} h4`]) {
    const fonts = await platformFonts(page, selector);
    expect(fonts.some(font => font.isCustomFont && font.familyName.includes("Inter") && font.glyphCount > 0)).toBe(true);
    if (selector.endsWith(" em")) await expect(page.locator(selector)).toHaveCSS("font-style", "italic");
  }
  await expect(page.locator(answerSelector)).toContainText("İ ı Ğ ğ Ş ş Ç ç Ö ö Ü ü");
  for (const prose of await page.locator(proseSelector).all()) {
    await expect(prose).toHaveCSS("font-size", "17px");
    await expect(prose).toHaveCSS("line-height", "28.05px");
    await expect(prose).toHaveCSS("white-space", "normal");
  }
  const sizes = await page.locator(`${answerSelector} :is(h1,h2,h3,h4,h5,h6)`).evaluateAll(nodes => nodes.map(node => parseFloat(getComputedStyle(node).fontSize)));
  expect(sizes).toHaveLength(6);
  expect(sizes[0]).toBeCloseTo(25.5);
  for (let index = 1; index < sizes.length; index++) expect(sizes[index]).toBeLessThanOrEqual(sizes[index - 1]);
  expect(sizes[3]).toBeGreaterThan(sizes[4]);
  await expect(page.locator(`${answerSelector} > h1`)).toHaveCSS("margin-top", "0px");
  const paragraph = page.locator(`${answerSelector} > p`).first();
  await expect(paragraph).toHaveCSS("margin-bottom", "17px");
  await expect(paragraph.locator("br")).toHaveCount(0);
  await expect(page.locator(".conversation__bubble")).toHaveCSS("font-size", "13px");
  expect(await page.locator(".conversation__bubble").evaluate(node => getComputedStyle(node).fontFamily)).not.toContain("Source Serif");
  for (const selector of [".code-card__copy", ".code-card__lang", ".code-card__toggle", ".markdown__image-remote"]) {
    const typography = await page.locator(selector).evaluate(node => {
      const read = () => {
        const style = getComputedStyle(node);
        return { family: style.fontFamily, size: style.fontSize, lineHeight: style.lineHeight };
      };
      const assistant = node.closest(".conversation__message--assistant")!;
      const actual = read();
      assistant.classList.remove("conversation__message--assistant");
      const original = read();
      assistant.classList.add("conversation__message--assistant");
      return { actual, original };
    });
    expect(typography.actual).toEqual(typography.original);
    expect(typography.actual.family).not.toContain("Source Serif");
  }
  await expect(page.locator(".code-card__copy")).toHaveCSS("font-size", "12px");
  await expect(page.locator(".markdown__image-remote")).toHaveCSS("font-size", "13px");
  await expect(page.getByRole("button", { name: "ornek.ts", exact: true })).toHaveCSS("font-size", "12px");
  const mono = await platformFonts(page, ".code-card__name");
  expect(mono.some(font => font.isCustomFont && font.familyName.includes("JetBrains"))).toBe(true);
  await expect(page.locator(".markdown__inline-code")).toHaveCSS("font-size", "13px");
  await expect(page.locator(".code-card code")).toHaveCSS("line-height", "20.8px");
  await expect(page.locator(".code-card code")).toHaveCSS("white-space", "pre");
  await expect(page.locator(".code-card__line").nth(1)).toBeAttached();
  const codeLinePitch = await page.locator(".code-card__line").evaluateAll(nodes => nodes[1].getBoundingClientRect().top - nodes[0].getBoundingClientRect().top);
  expect(codeLinePitch).toBeCloseTo(20.8, 1);
  await expect(page.locator(`${answerSelector} table`)).toHaveCSS("font-size", "14px");
  const tableFonts = await platformFonts(page, `${answerSelector} td`);
  expect(tableFonts.some(font => font.isCustomFont && font.familyName.includes("Inter"))).toBe(true);
});

for (const theme of ["light", "dark"]) {
  test(`okuma düzeni ve sınırlı taşma ${theme}`, async ({ page }) => {
    await openTypography(page, theme);
    const measurements = await page.locator(answerSelector).evaluate(node => {
      const stream = node.closest(".conversation__stream")!;
      const ruler = document.createElement("span");
      ruler.style.cssText = "display:block;width:72ch;position:absolute;visibility:hidden";
      node.append(ruler);
      const width = ruler.getBoundingClientRect().width;
      ruler.remove();
      return { width: node.getBoundingClientRect().width, limit: width, left: node.getBoundingClientRect().left, streamLeft: stream.getBoundingClientRect().left };
    });
    expect(measurements.width).toBeLessThanOrEqual(measurements.limit + 1);
    expect(measurements.left - measurements.streamLeft).toBe(8);
    await expect(page.locator(".conversation")).toHaveScreenshot(`typography-${theme}-desktop.png`, { maxDiffPixelRatio: 0 });
    await page.locator(".conversation").evaluate(node => {
      const heading = node.querySelector("h3")!;
      node.scrollTop += heading.getBoundingClientRect().top - node.getBoundingClientRect().top - 16;
      node.dispatchEvent(new Event("scroll"));
    });
    await expect(page.locator(".conversation")).toHaveScreenshot(`typography-${theme}-headings-lists.png`, { maxDiffPixelRatio: 0 });
    await page.locator(".code-card").scrollIntoViewIfNeeded();
    for (const selector of [".markdown__table-scroll", ".code-card__body"]) {
      const bounds = await page.locator(selector).evaluate(node => ({ width: node.clientWidth, scroll: node.scrollWidth, parent: node.closest(".markdown")!.clientWidth }));
      expect(bounds.width).toBeLessThanOrEqual(bounds.parent);
      expect(bounds.scroll).toBeGreaterThan(bounds.width);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.locator(".conversation").evaluate(node => {
      node.scrollTop = node.scrollHeight;
      node.dispatchEvent(new Event("scroll"));
    });
    await expect(page.locator(".conversation")).toHaveScreenshot(`typography-${theme}-details.png`, { maxDiffPixelRatio: 0 });
    // Geniş pencere içinde gerçek konuşma konteyneri daraltılır.
    await page.locator(".app-shell__main").evaluate(node => { (node as HTMLElement).style.width = "600px"; });
    await expect(page.locator(answerSelector)).toHaveCSS("font-size", "16px");
    await expect(page.locator(answerSelector)).toHaveCSS("line-height", "25.6px");
    for (const selector of [".markdown__table-scroll", ".code-card__body"]) {
      expect(await page.locator(selector).evaluate(node => node.clientWidth <= node.closest(".markdown")!.clientWidth)).toBe(true);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.locator(".conversation").evaluate(node => {
    (node as HTMLElement).style.scrollBehavior = "auto";
    node.scrollTop = 0;
    node.dispatchEvent(new Event("scroll"));
  });
  await expect.poll(() => page.locator(".conversation").evaluate(node => node.scrollTop)).toBe(0);
    await expect(page.locator(".conversation")).toHaveScreenshot(`typography-${theme}-narrow-container.png`, { maxDiffPixelRatio: 0 });
  });
}

test("erişilebilir ölçek yüzde 125 büyür", async ({ page }) => {
  await openTypography(page);
  await page.evaluate(() => { document.documentElement.style.fontSize = "125%"; });
  await expect(page.locator(answerSelector)).toHaveCSS("font-size", "21.25px");
  await expect(page.locator(".markdown__inline-code")).toHaveCSS("font-size", "16.25px");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test("akış sırasında ara anlatım ve büyüyen yanıt Inter kalır", async ({ page }) => {
  await page.clock.install();
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.goto("/e2e/preview.html?state=typography&streaming=1&inspector=0&sidebar=0");
  const prose = page.locator(answerSelector);
  const initial = (await prose.textContent())!.length;
  await page.clock.runFor(500);
  expect((await prose.textContent())!.length).toBeGreaterThan(initial);
  await expect(prose).toHaveCSS("font-size", "17px");
  await expect(page.locator(".conversation__message--narration .markdown")).toHaveCSS("font-size", "17px");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
});

test("eski video önizleme bağlantısı çalışan görsel ekranını açar", async ({ page }) => {
  await page.goto("/e2e/preview.html?state=video&inspector=0&sidebar=0");
  await expect(page.getByRole("region", { name: "Görsel oluştur", exact: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Nasıl bir görsel istiyorsun?" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Video", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Yakında" })).toHaveCount(0);
});
