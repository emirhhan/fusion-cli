import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import { DEFAULT_KEYMAP, effectiveBindings, eventToKey, isMacPlatform, keymapFromPayload, type Keymap } from "./keys";

/** Ayarlar › Kısayollar bir bağı değiştirince yayınlanan pencere olayı (yük: `kisayol.*` yanıtı). */
export const KEYMAP_CHANGED_EVENT = "fusion:kisayollar-degisti";
/** Son okunan tablo (çekirdek yokken geçerli olan); yalnız bu cihazın kolaylığı, kaynak dosyadır. */
export const KEYMAP_CACHE_KEY = "fusion.kisayollar.son";
/** Bu özniteliği taşıyan öğenin içinde (tuş kaydı alanı) global kısayollar çalışmaz. */
export const SHORTCUT_CAPTURE_ATTRIBUTE = "data-kisayol-kaydi";

interface KeymapClient {
  request(name: string, data: Record<string, unknown>): Promise<unknown>;
}

function readCachedKeymap(): Keymap {
  try {
    const raw = localStorage.getItem(KEYMAP_CACHE_KEY);
    return (raw && keymapFromPayload({ ...JSON.parse(raw), ok: true })) || DEFAULT_KEYMAP;
  } catch {
    return DEFAULT_KEYMAP; // Bozuk ya da erişilemeyen depo: varsayılanlar.
  }
}

function cacheKeymap(keymap: Keymap): void {
  try { localStorage.setItem(KEYMAP_CACHE_KEY, JSON.stringify(keymap)); } catch { /* depo kapalı: önbelleksiz devam */ }
}

/**
 * Etkin tuş tablosu: çekirdekten `kisayol.liste` ile okunur; pencere odağa dönünce yeniden okunur
 * (dosya elle düzenlendiyse yeniden başlatmadan uygulanır).
 *
 * Ölçüldü (31 Ekim): etkin oturum yokken (boş ekran, çekirdek bağlanmadan) varsayılan tabloya
 * düşülüyordu; artık son okunan tablo yerelde tutulur ve çekirdek yokken o geçerlidir.
 */
export function useKeymap(client: KeymapClient | null): Keymap {
  const [keymap, setKeymap] = useState<Keymap>(readCachedKeymap);
  const sequence = useRef(0);
  const accept = useCallback((next: Keymap) => { setKeymap(next); cacheKeymap(next); }, []);
  const reload = useCallback(() => {
    if (!client) return;
    const current = ++sequence.current;
    void client.request("kisayol.liste", {}).then((payload) => {
      const next = keymapFromPayload(payload);
      if (next && current === sequence.current) accept(next);
    }).catch(() => undefined); // Eski çekirdek bu isteği tanımaz: son bilinen tablo kalır.
  }, [accept, client]);
  useEffect(() => {
    reload();
    const onChanged = (event: Event) => {
      const next = keymapFromPayload((event as CustomEvent<unknown>).detail);
      if (next) { sequence.current += 1; accept(next); }
    };
    window.addEventListener("focus", reload);
    window.addEventListener(KEYMAP_CHANGED_EVENT, onChanged);
    return () => {
      window.removeEventListener("focus", reload);
      window.removeEventListener(KEYMAP_CHANGED_EVENT, onChanged);
    };
  }, [accept, reload]);
  return keymap;
}

/** xterm'in odak öğesi bu seçicinin içindedir. */
const TERMINAL_SELECTOR = ".xterm";

/**
 * Windows/Linux'ta terminal odaktayken uygulamaya geçen bağlar. Ölçüldü (31 Ekim): xterm Ctrl+harfi
 * kabuğa gönderip olayı durdurduğu için terminal Ctrl+J ile kapatılamıyordu. VS Code'un
 * "kabuğu atla" modeli: terminali aç/kapat tuşu ve Ctrl+Shift bağları (kabuk Ctrl+Shift+J'yi
 * Ctrl+J'den ayıramaz) uygulamanındır; Ctrl+K/Ctrl+P/Ctrl+B gibi okuma satırı tuşları kabukta kalır.
 */
function passesTerminal(key: string, action: string): boolean {
  return action === "terminal" || /(^|\+)shift\+/.test(key);
}

/**
 * Tek global dinleyici (P-046). İşleyici eylemi işlediyse `true` döner; o zaman tarayıcının
 * kendi davranışı (Ctrl+P yazdır, Ctrl+N yeni pencere) engellenir.
 *
 * `defaultPrevented` olay atlanır: terminal ⌘K'yı kendi "temizle"si için yakalar ve işaretler.
 * Windows/Linux'ta terminal odaktayken `passesTerminal` bağları xterm'den ÖNCE (yakalama evresinde)
 * işlenir.
 */
export function useGlobalShortcuts(
  baglar: Record<string, string>,
  handlerRef: MutableRefObject<(action: string) => boolean>,
  mac: boolean = isMacPlatform(),
): void {
  useEffect(() => {
    const table = effectiveBindings(baglar, mac);
    const resolve = (event: KeyboardEvent): [string, string] | null => {
      if (event.defaultPrevented || event.isComposing || event.repeat) return null;
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest(`[${SHORTCUT_CAPTURE_ATTRIBUTE}]`)) return null;
      const key = eventToKey(event, mac);
      const action = key ? table.get(key) : undefined;
      return key && action ? [key, action] : null;
    };
    const run = (event: KeyboardEvent, action: string) => {
      if (!handlerRef.current(action)) return;
      event.preventDefault();
      event.stopPropagation();
    };
    const onKey = (event: KeyboardEvent) => {
      const found = resolve(event);
      if (found) run(event, found[1]);
    };
    const onTerminalKey = (event: KeyboardEvent) => {
      if (!(event.target instanceof Element) || !event.target.closest(TERMINAL_SELECTOR)) return;
      const found = resolve(event);
      if (found && passesTerminal(...found)) run(event, found[1]);
    };
    window.addEventListener("keydown", onKey);
    if (!mac) window.addEventListener("keydown", onTerminalKey, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keydown", onTerminalKey, true);
    };
  }, [baglar, handlerRef, mac]);
}
