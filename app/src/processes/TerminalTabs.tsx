import { useEffect, useRef, useState } from "react";
import { Icon } from "../ui/Icon";
import { XtermSession } from "./XtermSession";
import { terminalRuntime, type TerminalRuntime, type TerminalSession } from "./terminalBridge";

interface TerminalTab {
  title: string;
  session: TerminalSession;
  closedReason: string | null;
  stopClosed: () => void;
}

export function TerminalTabs({ cwd, runtime = terminalRuntime }: { cwd: string; runtime?: TerminalRuntime }) {
  const [tabs, setTabs] = useState<TerminalTab[]>([]);
  const tabsRef = useRef<TerminalTab[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);
  const nextNumber = useRef(1);
  const mountedRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const owned = tabsRef.current;
      tabsRef.current = [];
      owned.forEach((tab) => {
        tab.stopClosed();
        if (tab.closedReason === null) void tab.session.close().finally(() => tab.session.dispose());
        else tab.session.dispose();
      });
    };
  }, []);

  const openTerminal = async () => {
    if (opening) return;
    setOpening(true);
    setError(null);
    try {
      const session = await runtime.openSession(cwd, 80, 24);
      if (!mountedRef.current) {
        await session.close().finally(() => session.dispose());
        return;
      }
      const tab: TerminalTab = {
        session,
        title: `Terminal ${nextNumber.current++}`,
        closedReason: null,
        stopClosed: () => undefined,
      };
      tab.stopClosed = session.onClosed((reason) => {
        tab.closedReason = reason;
        setTabs((current) => current.map((item) => item === tab ? { ...item, closedReason: reason } : item));
      });
      tabsRef.current = [...tabsRef.current, tab];
      setTabs((current) => [...current, tab]);
      setActiveId(session.snapshot.terminalId);
    } catch (reason) {
      if (mountedRef.current) setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      if (mountedRef.current) setOpening(false);
    }
  };

  const closeActive = async () => {
    if (!activeId) return;
    const closingIndex = tabs.findIndex((tab) => tab.session.snapshot.terminalId === activeId);
    const tab = tabs[closingIndex];
    if (!tab) return;
    try {
      if (tab.closedReason === null) await tab.session.close();
      const remaining = tabs.filter((item) => item !== tab);
      tabsRef.current = tabsRef.current.filter((item) => item !== tab);
      tab.stopClosed();
      tab.session.dispose();
      setTabs(remaining);
      setActiveId(remaining[Math.min(closingIndex, remaining.length - 1)]?.session.snapshot.terminalId ?? null);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const selectIndex = (index: number) => {
    const tab = tabs[(index + tabs.length) % tabs.length];
    if (!tab) return;
    const terminalId = tab.session.snapshot.terminalId;
    setActiveId(terminalId);
    window.requestAnimationFrame(() => document.getElementById(`terminal-tab-${terminalId}`)?.focus());
  };

  return (
    <div className="terminal-tabs">
      <div className="terminal-tabs__strip">
        <div aria-label="Terminal oturumları" className="terminal-tabs__list" role="tablist">
          {tabs.map((tab, index) => {
            const { terminalId, cwd: terminalCwd, pid } = tab.session.snapshot;
            return (
              <button
                aria-controls={`terminal-panel-${terminalId}`}
                aria-label={tab.title}
                aria-selected={activeId === terminalId}
                className="terminal-tabs__tab"
                id={`terminal-tab-${terminalId}`}
                key={terminalId}
                onClick={() => setActiveId(terminalId)}
                onKeyDown={(event) => {
                  if (event.key === "ArrowLeft") { event.preventDefault(); selectIndex(index - 1); }
                  else if (event.key === "ArrowRight") { event.preventDefault(); selectIndex(index + 1); }
                  else if (event.key === "Home") { event.preventDefault(); selectIndex(0); }
                  else if (event.key === "End") { event.preventDefault(); selectIndex(tabs.length - 1); }
                }}
                role="tab"
                tabIndex={activeId === terminalId ? 0 : -1}
                title={`${terminalCwd} · ${tab.closedReason ? `Kapandı: ${tab.closedReason}` : `PID ${pid ?? "—"}`}`}
                type="button"
              >
                <span className={`terminal-tabs__dot terminal-tabs__dot--${tab.closedReason ? "bitti" : "calisiyor"}`} />
                <span>{tab.title}</span>
                {tab.closedReason && <span className="terminal-tabs__state">Kapandı</span>}
              </button>
            );
          })}
        </div>
        <button aria-label="Yeni terminal" className="terminal-tabs__new" disabled={opening} onClick={() => void openTerminal()} title="Yeni terminal" type="button">
          <Icon name="new" size={16} />
        </button>
        <button aria-label="Aktif terminali kapat" className="terminal-tabs__close" disabled={!activeId} onClick={() => void closeActive()} title="Terminali kapat" type="button">×</button>
      </div>

      {error && <p className="process-error" role="alert">{error}</p>}
      {tabs.length ? tabs.map((tab) => {
        const terminalId = tab.session.snapshot.terminalId;
        return (
          <section aria-label={`${tab.title} ekranı`} hidden={activeId !== terminalId} id={`terminal-panel-${terminalId}`} key={terminalId} role="tabpanel">
            <XtermSession active={activeId === terminalId} closedReason={tab.closedReason} session={tab.session} />
          </section>
        );
      }) : (
        <div className="terminal-tabs__empty">
          <Icon name="terminal" size={24} />
          <p>Bu çalışma alanında henüz terminal açılmadı.</p>
          <button disabled={opening} onClick={() => void openTerminal()} type="button">İlk terminali aç</button>
        </div>
      )}
    </div>
  );
}
