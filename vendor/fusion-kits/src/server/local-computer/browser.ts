import type { Browser, BrowserContext, Page } from 'playwright';
import type { SessionState } from '../../shared/fusion-profile.js';
import { ConflictError, OperationError } from './errors.js';
import { isPrivateHost, PRIVATE_HOST_MESSAGE } from './network-guard.js';

export const VIEWPORT = { width: 1280, height: 720 };
const MAX_TEXT = 50_000;
const MAX_ELEMENTS = 300;
const ACTION_TIMEOUT_MS = 10_000;
const NAVIGATE_TIMEOUT_MS = 30_000;
const REF_ATTRIBUTE = 'data-kits-ref';
const REF_PATTERN = /^e\d+$/;
const INTERACTIVE =
  'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=checkbox],[role=menuitem],[role=tab],[role=textbox],[role=combobox],[contenteditable=""],[contenteditable=true],[onclick]';

export interface SnapshotElement {
  ref: string;
  role: string;
  name: string;
  type?: string;
  value?: string;
  href?: string;
  disabled?: boolean;
}
export interface BrowserSnapshot {
  snapshotId: number;
  url: string;
  title: string;
  elements: SnapshotElement[];
  truncated: boolean;
}
export interface BrowserScreenshot {
  base64: string;
  width: number;
  height: number;
  url: string;
  capturedAt: number;
}

/** Sayfa eylemleri. Gerçeği Playwright; testlerde sahtesi enjekte edilir. */
export interface KitBrowser {
  navigate(url: string): Promise<{ url: string; title: string }>;
  read(): Promise<{ url: string; title: string; text: string }>;
  snapshot(): Promise<BrowserSnapshot>;
  screenshot(): Promise<BrowserScreenshot>;
  click(ref: string, snapshotId: number): Promise<{ url: string }>;
  type(
    ref: string,
    snapshotId: number,
    text: string,
    submit?: boolean,
  ): Promise<{ url: string }>;
  key(key: string): Promise<{ url: string }>;
  scroll(deltaY: number): Promise<{ url: string }>;
  humanClick(x: number, y: number): Promise<{ url: string }>;
  humanType(text: string): Promise<{ url: string }>;
  humanKey(key: string): Promise<{ url: string }>;
  humanScroll(deltaY: number): Promise<{ url: string }>;
  close(): Promise<void>;
}

/** Profil klasörünü alıp tarayıcıyı açar. `session` verilirse (Fusion profili, P-023)
 * kalıcı profil KULLANILMAZ: bağlam yalnız bellektedir, kapanınca oturum silinir. */
export type BrowserFactory = (
  profileDir: string,
  session?: SessionState,
) => Promise<KitBrowser>;

/** Oturum yükleme hatası: Playwright iletisi çerez alanı içerebilir, dışarı sabit metin çıkar. */
export const SESSION_LOAD_FAILED =
  'Fusion oturumu Kit tarayıcısına yüklenemedi; profili Fusion’da yeniden aktarıp tekrar dene.';

function failure(error: unknown): never {
  if (error instanceof ConflictError || error instanceof OperationError)
    throw error;
  const message = error instanceof Error ? error.message : String(error);
  throw new OperationError(
    `Tarayıcı işlemi başarısız: ${message.split('\n')[0].slice(0, 300)}`,
  );
}

/** Sayfadaki görünür etkileşimli öğelere e1, e2… işaretleri koyar. */
function collectElements(args: {
  selector: string;
  attribute: string;
  max: number;
}) {
  document
    .querySelectorAll(`[${args.attribute}]`)
    .forEach((node) => node.removeAttribute(args.attribute));
  const elements: Record<string, unknown>[] = [];
  let truncated = false;
  for (const node of Array.from(document.querySelectorAll(args.selector))) {
    const box = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    if (!box.width || !box.height || style.visibility === 'hidden') continue;
    if (elements.length >= args.max) {
      truncated = true;
      break;
    }
    const ref = `e${elements.length + 1}`;
    node.setAttribute(args.attribute, ref);
    const input = node as HTMLInputElement;
    const tag = node.tagName.toLowerCase();
    const type = tag === 'input' ? input.type : undefined;
    const name =
      node.getAttribute('aria-label') ||
      (node as HTMLElement).innerText ||
      input.placeholder ||
      node.getAttribute('title') ||
      node.getAttribute('alt') ||
      input.value ||
      '';
    elements.push({
      ref,
      role:
        node.getAttribute('role') ||
        (tag === 'a' ? 'link' : tag === 'input' ? (type ?? 'input') : tag),
      name: name.replace(/\s+/g, ' ').trim().slice(0, 120),
      ...(type ? { type } : {}),
      // Parola alanlarının değeri asla dışarı verilmez.
      ...(input.value && type !== 'password'
        ? { value: input.value.slice(0, 120) }
        : {}),
      ...(tag === 'a' ? { href: (node as HTMLAnchorElement).href } : {}),
      ...(input.disabled ? { disabled: true } : {}),
    });
  }
  return { elements, truncated };
}

class PlaywrightBrowser implements KitBrowser {
  private snapshotId = 0;
  private snapshotted = false;

  constructor(
    private context: BrowserContext,
    private owner?: Browser,
  ) {}

  private async page(): Promise<Page> {
    const open = this.context.pages().filter((page) => !page.isClosed());
    return open.at(-1) ?? this.context.newPage();
  }

  private async run<T>(fn: (page: Page) => Promise<T>): Promise<T> {
    try {
      return await fn(await this.page());
    } catch (error) {
      return failure(error);
    }
  }

  private locator(page: Page, ref: string, snapshotId: number) {
    if (!REF_PATTERN.test(ref))
      throw new ConflictError('Geçersiz öğe işareti; yeni anlık görüntü al.');
    if (!this.snapshotted || snapshotId !== this.snapshotId)
      throw new ConflictError(
        'Anlık görüntü eski; computer_snapshot ile yenile.',
      );
    return page.locator(`[${REF_ATTRIBUTE}="${ref}"]`);
  }

  private async afterElement(
    page: Page,
    ref: string,
    action: () => Promise<void>,
  ) {
    try {
      await action();
    } catch (error) {
      if (/waiting for locator|strict mode violation/i.test(String(error)))
        throw new ConflictError(
          `${ref} sayfada artık yok; computer_snapshot ile yenile.`,
        );
      throw error;
    }
    return { url: page.url() };
  }

  navigate(url: string) {
    return this.run(async (page) => {
      const target = new URL(url);
      if (
        ['http:', 'https:'].includes(target.protocol) &&
        (await isPrivateHost(target.hostname))
      )
        throw new OperationError(PRIVATE_HOST_MESSAGE);
      await page.goto(url, {
        waitUntil: 'domcontentloaded',
        timeout: NAVIGATE_TIMEOUT_MS,
      });
      this.snapshotted = false;
      return { url: page.url(), title: await page.title() };
    });
  }

  read() {
    return this.run(async (page) => ({
      url: page.url(),
      title: await page.title(),
      text: (await page.evaluate(() => document.body?.innerText ?? '')).slice(
        0,
        MAX_TEXT,
      ),
    }));
  }

  snapshot() {
    return this.run(async (page) => {
      const found = await page.evaluate(collectElements, {
        selector: INTERACTIVE,
        attribute: REF_ATTRIBUTE,
        max: MAX_ELEMENTS,
      });
      this.snapshotId += 1;
      this.snapshotted = true;
      return {
        snapshotId: this.snapshotId,
        url: page.url(),
        title: await page.title(),
        elements: found.elements as unknown as SnapshotElement[],
        truncated: found.truncated,
      };
    });
  }

  screenshot() {
    return this.run(async (page) => {
      const png = await page.screenshot({ type: 'png' });
      const size = page.viewportSize() ?? VIEWPORT;
      return {
        base64: png.toString('base64'),
        width: size.width,
        height: size.height,
        url: page.url(),
        capturedAt: Date.now(),
      };
    });
  }

  click(ref: string, snapshotId: number) {
    return this.run(async (page) => {
      const target = this.locator(page, ref, snapshotId);
      return this.afterElement(page, ref, () =>
        target.click({ timeout: ACTION_TIMEOUT_MS }),
      );
    });
  }

  type(ref: string, snapshotId: number, text: string, submit?: boolean) {
    return this.run(async (page) => {
      const target = this.locator(page, ref, snapshotId);
      return this.afterElement(page, ref, async () => {
        await target.fill(text, { timeout: ACTION_TIMEOUT_MS });
        if (submit) await target.press('Enter', { timeout: ACTION_TIMEOUT_MS });
      });
    });
  }

  key(key: string) {
    return this.run(async (page) => {
      await page.keyboard.press(key);
      return { url: page.url() };
    });
  }

  scroll(deltaY: number) {
    return this.run(async (page) => {
      await page.mouse.wheel(0, deltaY);
      return { url: page.url() };
    });
  }

  humanClick(x: number, y: number) {
    return this.run(async (page) => {
      await page.mouse.click(x, y);
      return { url: page.url() };
    });
  }

  humanType(text: string) {
    return this.run(async (page) => {
      await page.keyboard.type(text);
      return { url: page.url() };
    });
  }

  humanKey(key: string) {
    return this.key(key);
  }

  humanScroll(deltaY: number) {
    return this.scroll(deltaY);
  }

  async close() {
    await this.context.close().catch(() => undefined);
    await this.owner?.close().catch(() => undefined);
  }
}

async function guardPrivateHosts(context: BrowserContext) {
  await context.route('**/*', async (route) => {
    const { protocol, hostname } = new URL(route.request().url());
    if (['http:', 'https:', 'ws:', 'wss:'].includes(protocol))
      if (await isPrivateHost(hostname)) return route.abort('blockedbyclient');
    return route.continue();
  });
}

const LAUNCH = { headless: true, args: ['--disable-gpu'] };

/** Fusion oturumuyla: kalıcı olmayan bağlam (çerezler yalnız bellekte, diske yazılmaz). */
async function sessionBrowser(session: SessionState) {
  const { chromium } = await import('playwright');
  const browser = await chromium.launch(LAUNCH);
  try {
    const context = await browser.newContext({
      viewport: VIEWPORT,
      storageState: session,
    });
    await guardPrivateHosts(context);
    return new PlaywrightBrowser(context, browser);
  } catch (error) {
    await browser.close().catch(() => undefined);
    if (/Executable doesn't exist/i.test(String(error))) throw error;
    // Playwright'ın iletisi çerez adını/değerini yansıtabilir: sabit metin dışarı çıkar.
    throw new OperationError(SESSION_LOAD_FAILED);
  }
}

export const playwrightBrowserFactory: BrowserFactory = async (
  profileDir,
  session,
) => {
  const { chromium } = await import('playwright');
  try {
    if (session) return await sessionBrowser(session);
    const context = await chromium.launchPersistentContext(profileDir, {
      ...LAUNCH,
      viewport: VIEWPORT,
    });
    await guardPrivateHosts(context);
    return new PlaywrightBrowser(context);
  } catch (error) {
    if (/Executable doesn't exist/i.test(String(error)))
      throw new OperationError(
        'Chromium kurulu değil; `npx playwright install chromium` ile kur.',
      );
    throw error;
  }
};
