import { useCallback, useLayoutEffect, useState, type RefObject } from "react";

interface PanelPlacement {
  host: HTMLElement;
  top: number;
  left: number;
  width: number;
  maxHeight: number;
}

/** Sohbetin gerçek kaydırma görünümünde kalan, akışı büyütmeyen pencere konumu. */
export function useActivityPanelPlacement(anchor: RefObject<HTMLElement | null>, open: boolean, watchPreview: boolean) {
  const [placement, setPlacement] = useState<PanelPlacement | null>(null);
  const [placeholderHeight, setPlaceholderHeight] = useState(0);
  const refresh = useCallback(() => {
    const element = anchor.current;
    const conversation = element?.closest<HTMLElement>(".conversation");
    const host = conversation?.closest<HTMLElement>(".conversation-frame");
    if (!element || !conversation || !host) return;
    const box = element.getBoundingClientRect();
    if (!open) setPlaceholderHeight(current => current === box.height ? current : box.height);
    const viewport = conversation.getBoundingClientRect();
    // Yerleşimsiz test/kapalı görünümde mevcut satır gösterimi kullanılabilir.
    if (viewport.width <= 0 || viewport.height <= 0) { setPlacement(null); return; }
    const hostBox = host.getBoundingClientRect();
    const top = Math.max(0, viewport.top) + 8;
    const bottom = Math.min(window.innerHeight, viewport.bottom) - 8;
    const width = Math.min(box.width, viewport.width - 16);
    const maxHeight = Math.min(470, Math.max(0, bottom - top));
    const left = Math.max(viewport.left + 8, Math.min(box.left, viewport.right - 8 - width));
    const next: PanelPlacement = {
      host, width, maxHeight,
      left: left - hostBox.left,
      top: Math.max(top, Math.min(box.top, bottom - maxHeight)) - hostBox.top,
    };
    setPlacement(current => current && current.host === next.host && current.top === next.top
      && current.left === next.left && current.width === next.width && current.maxHeight === next.maxHeight ? current : next);
  }, [anchor, open]);

  useLayoutEffect(() => {
    // Kapalı geçmiş turları her sohbet kaydırmasında ölçüm/dinleyici üretmez.
    if (!open && !watchPreview) return;
    refresh();
    const element = anchor.current;
    const conversation = element?.closest<HTMLElement>(".conversation");
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(refresh);
    if (element) observer?.observe(element);
    if (!open) return () => observer?.disconnect();
    if (conversation) observer?.observe(conversation);
    conversation?.addEventListener("scroll", refresh, { passive: true });
    window.addEventListener("resize", refresh);
    window.visualViewport?.addEventListener("resize", refresh);
    return () => {
      observer?.disconnect();
      conversation?.removeEventListener("scroll", refresh);
      window.removeEventListener("resize", refresh);
      window.visualViewport?.removeEventListener("resize", refresh);
    };
  }, [anchor, open, watchPreview, refresh]);
  return { placement, placeholderHeight, refresh };
}
