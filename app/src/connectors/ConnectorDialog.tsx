import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

export function ConnectorDialog({ children, label, onClose }: { children: ReactNode; label: string; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const siblings = [...document.body.children].filter((node): node is HTMLElement => node instanceof HTMLElement && !node.contains(ref.current));
    const inert = siblings.map((node) => node.inert);
    siblings.forEach((node) => { node.inert = true; });
    const controls = () => [...(ref.current?.querySelectorAll<HTMLElement>('input:not(:disabled), select:not(:disabled), button:not(:disabled), [tabindex="0"]') ?? [])];
    (ref.current?.querySelector<HTMLElement>("input, select") ?? ref.current)?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); close.current(); }
      if (event.key !== "Tab") return;
      const items = controls();
      const first = items[0];
      const last = items[items.length - 1];
      if (!first) { event.preventDefault(); ref.current?.focus(); }
      else if (event.shiftKey && (document.activeElement === first || !ref.current?.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !ref.current?.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    };
    window.addEventListener("keydown", keydown);
    return () => {
      window.removeEventListener("keydown", keydown);
      siblings.forEach((node, index) => { node.inert = inert[index]; });
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return createPortal(<div className="connector-dialog__backdrop"><div aria-label={label} aria-modal="true" className="connector-dialog" ref={ref} role="dialog" tabIndex={-1}>{children}</div></div>, document.body);
}
