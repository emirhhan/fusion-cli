/**
 * Browser ⋮ › "Open links in built-in browser" (#439; Claude Code Desktop).
 *
 * Açıkken sohbetteki http(s) bağlantıları sistem tarayıcısı yerine uygulama içi Tarayıcı
 * bölmesinde açılır. Tercih bu bilgisayarda saklanır; bağlantı tıklaması bir pencere olayıyla
 * Tarayıcı bölmesine iletilir (`useBrowserInspector` dinler).
 */
export const OPEN_LINKS_KEY = "fusion.browser.open-links-inside";
export const OPEN_IN_BROWSER_EVENT = "fusion:tarayicida-ac";

export function readOpenLinksInside(storage: Pick<Storage, "getItem"> = localStorage): boolean {
  try { return storage.getItem(OPEN_LINKS_KEY) === "true"; } catch { return false; }
}

export function saveOpenLinksInside(value: boolean, storage: Pick<Storage, "setItem"> = localStorage): void {
  try { storage.setItem(OPEN_LINKS_KEY, String(value)); } catch { /* bu pencerede geçerli kalır */ }
}

/** Bağlantı Tarayıcı bölmesine yönlendirildiyse true (çağıran varsayılan açılışı durdurur). */
export function routeLinkToBrowser(href: string): boolean {
  if (!/^https?:\/\//i.test(href) || !readOpenLinksInside()) return false;
  window.dispatchEvent(new CustomEvent(OPEN_IN_BROWSER_EVENT, { detail: { url: href } }));
  return true;
}
