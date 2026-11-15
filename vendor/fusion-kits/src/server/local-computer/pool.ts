import type { SessionState } from '../../shared/fusion-profile.js';
import type { BrowserFactory, KitBrowser } from './browser.js';

export const IDLE_CLOSE_MS = 10 * 60 * 1000;

/**
 * Aynı anda en fazla bir Kit tarayıcısı açık tutar (8 GB makine koruması).
 * Tarayıcı ilk kullanımda açılır, boşta kalınca kapanır. Eylemler sırayla çalışır.
 */
export class BrowserPool {
  private current?: { id: string; browser: KitBrowser; session?: string };
  private timer?: ReturnType<typeof setTimeout>;
  private chain: Promise<unknown> = Promise.resolve();

  constructor(
    private factory: BrowserFactory,
    private idleMs = IDLE_CLOSE_MS,
  ) {}

  get openId() {
    return this.current?.id;
  }

  /** Boşta sayacını sıfırlamadan, yalnız o Kit'in açık tarayıcısını verir. */
  peek(id: string) {
    return this.current?.id === id ? this.current.browser : undefined;
  }

  use<T>(
    id: string,
    profileDir: string,
    fn: (browser: KitBrowser) => Promise<T>,
  ): Promise<T> {
    return this.exclusive(async () => {
      if (this.current?.id !== id) {
        await this.shutdown();
        this.current = { id, browser: await this.factory(profileDir) };
      }
      this.clearTimer();
      try {
        return await fn(this.current.browser);
      } finally {
        this.armTimer();
      }
    });
  }

  /** Bu Kit'te yüklü Fusion oturumunun profil adı; yoksa `undefined`. */
  sessionOf(id: string) {
    return this.current?.id === id ? this.current.session : undefined;
  }

  /**
   * Fusion oturumuyla (P-023) yeni, kalıcı olmayan bir tarayıcı aç; açık olanı kapatır.
   * Oturum yalnız bu nesnede ve tarayıcının belleğinde yaşar; kapanınca silinir.
   */
  load(id: string, profileDir: string, label: string, session: SessionState) {
    return this.exclusive(async () => {
      await this.shutdown();
      this.current = {
        id,
        browser: await this.factory(profileDir, session),
        session: label,
      };
      this.armTimer();
    });
  }

  release(id: string) {
    return this.exclusive(async () => {
      if (this.current?.id === id) await this.shutdown();
    });
  }

  close() {
    return this.exclusive(() => this.shutdown());
  }

  private exclusive<T>(task: () => Promise<T>): Promise<T> {
    const next = this.chain.then(task, task);
    this.chain = next.catch(() => undefined);
    return next;
  }

  private armTimer() {
    this.clearTimer();
    const id = this.current?.id ?? '';
    this.timer = setTimeout(() => void this.release(id), this.idleMs);
    this.timer.unref?.();
  }

  private clearTimer() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
  }

  private async shutdown() {
    this.clearTimer();
    const open = this.current;
    this.current = undefined;
    await open?.browser.close();
  }
}
