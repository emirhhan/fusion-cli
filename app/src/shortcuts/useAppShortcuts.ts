import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import { DEFAULT_KEYMAP, effectiveBindings, eventToKey, isMacPlatform, keymapFromPayload, type Keymap } from "./keys";

/** Ayarlar › Kısayollar bir bağı değiştirince yayınlanan pencere olayı (yük: `kisayol.*` yanıtı). */
export const KEYMAP_CHANGED_EVENT = "fusion:kisayollar-degisti";
/** Bu özniteliği taşıyan öğenin içinde (tuş kaydı alanı) global kısayollar çalışmaz. */
export const SHORTCUT_CAPTURE_ATTRIBUTE = "data-kisayol-kaydi";

interface KeymapClient {
  request(name: string, data: Record<string, unknown>): Promise<unknown>;
}

/**
 * Etkin tuş tablosu: çekirdekten `kisayol.liste` ile okunur; pencere odağa dönünce yeniden okunur
 * (dosya elle düzenlendiyse yeniden başlatmadan uygulanır). Çekirdek yoksa varsayılanlar geçerli.
 */
export function useKeymap(client: KeymapClient | null): Keymap {
  const [keymap, setKeymap] = useState<Keymap>(DEFAULT_KEYMAP);
  const sequence = useRef(0);
  const reload = useCallback(() => {
    if (!client) return;
    const current = ++sequence.current;
    void client.request("kisayol.liste", {}).then((payload) => {
      const next = keymapFromPayload(payload);
      if (next && current === sequence.current) setKeymap(next);
    }).catch(() => undefined); // Eski çekirdek bu isteği tanımaz: varsayılanlar kalır.
  }, [client]);
  useEffect(() => {
    reload();
    const onChanged = (event: Event) => {
      const next = keymapFromPayload((event as CustomEvent<unknown>).detail);
      if (next) { sequence.current += 1; setKeymap(next); }
    };
    window.addEventListener("focus", reload);
    window.addEventListener(KEYMAP_CHANGED_EVENT, onChanged);
    return () => {
      window.removeEventListener("focus", reload);
      window.removeEventListener(KEYMAP_CHANGED_EVENT, onChanged);
    };
  }, [reload]);
  return keymap;
}

/**
 * Tek global dinleyici (P-046). İşleyici eylemi işlediyse `true` döner; o zaman tarayıcının
 * kendi davranışı (Ctrl+P yazdır, Ctrl+N yeni pencere) engellenir.
 *
 * `defaultPrevented` olay atlanır: terminal ⌘K'yı kendi "temizle"si için yakalar ve işaretler.
 */
export function useGlobalShortcuts(
  baglar: Record<string, string>,
  handlerRef: MutableRefObject<(action: string) => boolean>,
  mac: boolean = isMacPlatform(),
): void {
  useEffect(() => {
    const table = effectiveBindings(baglar, mac);
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.repeat) return;
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest(`[${SHORTCUT_CAPTURE_ATTRIBUTE}]`)) return;
      const key = eventToKey(event, mac);
      const action = key ? table.get(key) : undefined;
      if (!action || !handlerRef.current(action)) return;
      event.preventDefault();
      event.stopPropagation();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [baglar, handlerRef, mac]);
}
