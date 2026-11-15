import { useEffect, useRef } from 'react';
/** Mobil çekmece açıldığında arka plan ve klavye odağı aynı sahibi izler. */
export function useMobileNavigation(
  open: boolean,
  setOpen: (open: boolean) => void,
) {
  const navigation = useRef<HTMLElement>(null);
  const workspace = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const nav = navigation.current;
    const opener = trigger.current;
    const background = workspace.current;
    if (!nav || !background) return;
    const inert = background.inert;
    const overflow = globalThis.document.body.style.overflow;
    background.inert = true;
    globalThis.document.body.style.overflow = 'hidden';
    const items = () =>
      [
        ...nav.querySelectorAll<HTMLElement>(
          'button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled])',
        ),
      ].filter((item) => item.getClientRects().length > 0);
    items()[0]?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
      }
      if (event.key !== 'Tab') return;
      const focusable = items();
      const first = focusable[0],
        last = focusable.at(-1);
      if (
        event.shiftKey &&
        (globalThis.document.activeElement === first ||
          !nav.contains(globalThis.document.activeElement))
      ) {
        event.preventDefault();
        last?.focus();
      } else if (
        !event.shiftKey &&
        (globalThis.document.activeElement === last ||
          !nav.contains(globalThis.document.activeElement))
      ) {
        event.preventDefault();
        first?.focus();
      }
    };
    const desktop = globalThis.matchMedia('(min-width: 701px)');
    const resize = () => {
      if (desktop.matches) setOpen(false);
    };
    globalThis.document.addEventListener('keydown', key);
    desktop.addEventListener('change', resize);
    resize();
    return () => {
      globalThis.document.removeEventListener('keydown', key);
      desktop.removeEventListener('change', resize);
      background.inert = inert;
      globalThis.document.body.style.overflow = overflow;
      opener?.focus();
    };
  }, [open, setOpen]);
  return { navigation, workspace, trigger };
}
