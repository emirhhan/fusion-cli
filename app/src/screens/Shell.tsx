import { useEffect, type ReactNode } from "react";
import "./Shell.css";

interface ShellProps {
  composer?: ReactNode;
  content: ReactNode;
  header?: ReactNode;
  inspector?: ReactNode;
  inspectorOpen?: boolean;
  onInspectorClose?: () => void;
  sidebar: ReactNode;
  sidebarCollapsed?: boolean;
}

export function Shell({
  composer,
  content,
  header,
  inspector,
  inspectorOpen = Boolean(inspector),
  onInspectorClose,
  sidebar,
  sidebarCollapsed = false,
}: ShellProps) {
  useEffect(() => {
    if (!inspectorOpen || !onInspectorClose) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onInspectorClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [inspectorOpen, onInspectorClose]);

  return (
    <div
      className="app-shell"
      data-inspector-open={inspectorOpen}
      data-sidebar-collapsed={sidebarCollapsed}
    >
      <aside aria-label="Ana navigasyon" className="app-shell__sidebar" id="fusion-sidebar" role="navigation">
        {sidebar}
      </aside>
      <section className="app-shell__workspace">
        {header && <header className="app-shell__header">{header}</header>}
        <main className="app-shell__main">{content}</main>
        {composer && <footer className="app-shell__composer">{composer}</footer>}
      </section>
      {inspector && (
        <aside aria-label="Denetçi" className="app-shell__inspector" id="fusion-inspector">
          {inspector}
        </aside>
      )}
      {inspector && inspectorOpen && (
        <button
          aria-label="Denetçiyi kapat"
          className="app-shell__backdrop"
          onClick={onInspectorClose}
          type="button"
        />
      )}
    </div>
  );
}
