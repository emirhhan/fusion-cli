import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import "./Shell.css";

const inspectorOverlayQuery = "(max-width: 1023px)";
const focusableSelector = [
  "a[href]",
  "area[href]",
  "button",
  "input",
  "select",
  "textarea",
  "summary",
  "iframe",
  "[tabindex]",
  '[contenteditable]:not([contenteditable="false"])',
  "audio[controls]",
  "video[controls]",
].join(",");

function getTabbableControls(container: HTMLElement | null) {
  if (!container) return [];
  return Array.from(container.querySelectorAll<HTMLElement>(focusableSelector)).filter((control) => {
    if (control.tabIndex < 0 || control.matches(":disabled") || control.hidden) return false;
    if (control.closest("[inert]") || control.getAttribute("aria-hidden") === "true") return false;
    if (control instanceof HTMLInputElement && control.type === "hidden") return false;
    const style = window.getComputedStyle(control);
    return style.display !== "none" && style.visibility !== "hidden";
  });
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => window.matchMedia?.(query).matches ?? false);

  useEffect(() => {
    if (!window.matchMedia) return;
    const media = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    setMatches(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

interface ShellProps {
  composer?: ReactNode;
  content: ReactNode;
  emptyChat?: boolean;
  header?: ReactNode;
  inspector?: ReactNode;
  inspectorCollapsed?: boolean;
  inspectorHeight?: number;
  inspectorOpen?: boolean;
  inspectorWidth?: number;
  onInspectorClose?: () => void;
  onSidebarClose?: () => void;
  sidebar: ReactNode;
  sidebarCollapsed?: boolean;
  /** Çalışma paneli sağda mı, görev kutusunun altında mı. */
  inspectorPlacement?: "right" | "bottom";
}

export function Shell({
  composer,
  content,
  emptyChat = false,
  header,
  inspector,
  inspectorCollapsed = false,
  inspectorHeight = 280,
  inspectorOpen = Boolean(inspector),
  inspectorWidth = 420,
  onInspectorClose,
  onSidebarClose,
  sidebar,
  sidebarCollapsed = false,
  inspectorPlacement = "right",
}: ShellProps) {
  const inspectorRef = useRef<HTMLElement>(null);
  const overlayOwnsFocus = useRef(false);
  const previousFocus = useRef<HTMLElement | null>(null);
  const inspectorOverlay = useMediaQuery(inspectorOverlayQuery);
  const sidebarOverlay = useMediaQuery("(max-width: 620px)");
  const inspectorModal = inspectorOpen && inspectorPlacement === "right" && inspectorOverlay && !inspectorCollapsed;
  const sidebarModal = sidebarOverlay && !sidebarCollapsed && !inspectorModal;
  const inspectorTrackWidth = inspectorCollapsed ? 56 : inspectorWidth;
  const restorePreviousFocus = useCallback(() => {
    const previous = previousFocus.current;
    previousFocus.current = null;
    overlayOwnsFocus.current = false;
    if (previous?.isConnected) previous.focus();
  }, []);

  useEffect(() => {
    if (!inspectorOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && onInspectorClose) {
        onInspectorClose();
        return;
      }
      if (!inspectorModal || event.key !== "Tab") return;
      const container = inspectorRef.current;
      if (!container) return;
      const controls = getTabbableControls(container);
      if (controls.length === 0) {
        event.preventDefault();
        container.focus();
        return;
      }
      const first = controls[0];
      const last = controls[controls.length - 1];
      const active = document.activeElement;
      if (active === container || !container.contains(active) || !controls.includes(active as HTMLElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [inspectorModal, inspectorOpen, onInspectorClose]);

  useEffect(() => {
    if (!sidebarModal || !onSidebarClose) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onSidebarClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onSidebarClose, sidebarModal]);

  useEffect(() => {
    if (inspectorModal && !overlayOwnsFocus.current) {
      const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      previousFocus.current = active && !inspectorRef.current?.contains(active) ? active : null;
      const [firstControl] = getTabbableControls(inspectorRef.current);
      (firstControl ?? inspectorRef.current)?.focus();
      overlayOwnsFocus.current = true;
    } else if (!inspectorModal && overlayOwnsFocus.current) {
      restorePreviousFocus();
    }
  }, [inspectorModal, restorePreviousFocus]);

  useEffect(() => {
    const container = inspectorRef.current;
    if (!inspectorModal || !container || !window.MutationObserver) return;
    const recaptureFocus = () => {
      const active = document.activeElement;
      if (active === container) return;
      const controls = getTabbableControls(container);
      if (!(active instanceof HTMLElement) || !controls.includes(active)) {
        (controls[0] ?? container).focus();
      }
    };
    const observer = new MutationObserver(recaptureFocus);
    observer.observe(container, {
      attributeFilter: ["aria-hidden", "disabled", "hidden", "style", "tabindex"],
      attributes: true,
      childList: true,
      subtree: true,
    });
    return () => observer.disconnect();
  }, [inspectorModal]);

  useEffect(() => () => restorePreviousFocus(), [restorePreviousFocus]);

  return (
    <div
      className="app-shell"
      data-inspector-open={inspectorOpen}
      data-inspector-overlay={inspectorOverlay}
      data-inspector-placement={inspectorPlacement}
      data-sidebar-collapsed={sidebarCollapsed}
      data-empty-chat={emptyChat}
      style={{
        "--inspector-width": `${inspectorTrackWidth}px`,
        "--inspector-bottom-height": inspectorCollapsed ? "56px" : `min(60dvh, ${inspectorHeight}px)`,
      } as CSSProperties}
    >
      <aside aria-label="Ana navigasyon" className="app-shell__sidebar" id="fusion-sidebar" role="navigation">
        {sidebar}
      </aside>
      <section className="app-shell__workspace">
        {header && <header className="app-shell__header">{header}</header>}
        {emptyChat && composer ? (
          <main className="app-shell__main">
            <div className="app-shell__welcome">
              {content}
              <div className="app-shell__composer">{composer}</div>
            </div>
          </main>
        ) : (
          <>
            <main className="app-shell__main">{content}</main>
            {composer && <footer className="app-shell__composer">{composer}</footer>}
          </>
        )}
      </section>
      {inspector && (
        <aside
          aria-label="Denetçi"
          className="app-shell__inspector"
          id="fusion-inspector"
          ref={inspectorRef}
          role={inspectorModal ? "dialog" : undefined}
          aria-modal={inspectorModal || undefined}
          tabIndex={-1}
        >
          {inspector}
        </aside>
      )}
      {inspector && inspectorModal && (
        <button
          aria-label="Denetçiyi kapat"
          className="app-shell__backdrop"
          onClick={onInspectorClose}
          type="button"
        />
      )}
      {sidebarModal && onSidebarClose && (
        <button
          aria-label="Navigasyonu kapat"
          className="app-shell__sidebar-backdrop"
          onClick={onSidebarClose}
          type="button"
        />
      )}
    </div>
  );
}
