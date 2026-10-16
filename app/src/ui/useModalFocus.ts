import { useEffect, useRef, type RefObject } from "react";

/** Portal diyaloğunda klavye odağını tut; kapanışta açan kontrole geri ver. */
export function useModalFocus(ref: RefObject<HTMLElement | null>, open: boolean, onClose: () => void, initialSelector = "input, select", onMissingReturn?: () => void) {
  const close = useRef(onClose);
  close.current = onClose;
  const fallback = useRef(onMissingReturn);
  fallback.current = onMissingReturn;
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const siblings = [...document.body.children].filter((node): node is HTMLElement => node instanceof HTMLElement && !node.contains(ref.current));
    const inert = siblings.map((node) => node.inert);
    siblings.forEach((node) => { node.inert = true; });
    const controls = () => [...(ref.current?.querySelectorAll<HTMLElement>('input:not(:disabled), select:not(:disabled), textarea:not(:disabled), button:not(:disabled), a[href], [tabindex="0"]') ?? [])]
      .filter((node) => !node.hidden && node.getAttribute("aria-hidden") !== "true");
    (ref.current?.querySelector<HTMLElement>(initialSelector) ?? ref.current)?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); close.current(); return; }
      if (event.key !== "Tab") return;
      const items = controls(), first = items[0], last = items[items.length - 1];
      if (!first) { event.preventDefault(); ref.current?.focus(); }
      else if (event.shiftKey && (document.activeElement === first || document.activeElement === ref.current || !ref.current?.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || document.activeElement === ref.current || !ref.current?.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", keydown);
    return () => {
      window.removeEventListener("keydown", keydown);
      siblings.forEach((node, index) => { node.inert = inert[index]; });
      if (previous?.isConnected) previous.focus(); else fallback.current?.();
    };
  }, [ref, open, initialSelector]);
}
