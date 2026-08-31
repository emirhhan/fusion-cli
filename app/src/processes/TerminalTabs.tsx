import { useRef, useState } from "react";
import { Icon } from "../ui/Icon";
import { XtermSession } from "./XtermSession";
import { terminalRuntime, type TerminalRuntime, type TerminalSnapshot } from "./terminalBridge";

interface TerminalTab extends TerminalSnapshot { title: string }

export function TerminalTabs({ cwd, runtime = terminalRuntime }: { cwd: string; runtime?: TerminalRuntime }) {
  const [tabs, setTabs] = useState<TerminalTab[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);
  const nextNumber = useRef(1);

  const openTerminal = async () => {
    if (opening) return;
    setOpening(true);
    setError(null);
    try {
      const snapshot = await runtime.open(cwd, 80, 24);
      const tab = { ...snapshot, title: `Terminal ${nextNumber.current++}` };
      setTabs((current) => [...current, tab]);
      setActiveId(tab.terminalId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setOpening(false);
    }
  };

  const closeActive = async () => {
    if (!activeId) return;
    const closingIndex = tabs.findIndex((tab) => tab.terminalId === activeId);
    try {
      await runtime.close(activeId);
      const remaining = tabs.filter((tab) => tab.terminalId !== activeId);
      setTabs(remaining);
      setActiveId(remaining[Math.min(closingIndex, remaining.length - 1)]?.terminalId ?? null);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const selectIndex = (index: number) => {
    const tab = tabs[(index + tabs.length) % tabs.length];
    if (!tab) return;
    setActiveId(tab.terminalId);
    window.requestAnimationFrame(() => document.getElementById(`terminal-tab-${tab.terminalId}`)?.focus());
  };

  return (
    <div className="terminal-tabs">
      <div className="terminal-tabs__strip">
        <div aria-label="Terminal oturumları" className="terminal-tabs__list" role="tablist">
          {tabs.map((tab, index) => (
            <button
              aria-controls={`terminal-panel-${tab.terminalId}`}
              aria-label={tab.title}
              aria-selected={activeId === tab.terminalId}
              className="terminal-tabs__tab"
              id={`terminal-tab-${tab.terminalId}`}
              key={tab.terminalId}
              onClick={() => setActiveId(tab.terminalId)}
              onKeyDown={(event) => {
                if (event.key === "ArrowLeft") { event.preventDefault(); selectIndex(index - 1); }
                else if (event.key === "ArrowRight") { event.preventDefault(); selectIndex(index + 1); }
                else if (event.key === "Home") { event.preventDefault(); selectIndex(0); }
                else if (event.key === "End") { event.preventDefault(); selectIndex(tabs.length - 1); }
              }}
              role="tab"
              tabIndex={activeId === tab.terminalId ? 0 : -1}
              title={`${tab.cwd} · PID ${tab.pid ?? "—"}`}
              type="button"
            >
              <span className="terminal-tabs__dot terminal-tabs__dot--calisiyor" />
              <span>{tab.title}</span>
            </button>
          ))}
        </div>
        <button aria-label="Yeni terminal" className="terminal-tabs__new" disabled={opening} onClick={() => void openTerminal()} title="Yeni terminal" type="button">
          <Icon name="new" size={16} />
        </button>
        <button aria-label="Aktif terminali kapat" className="terminal-tabs__close" disabled={!activeId} onClick={() => void closeActive()} title="Terminali kapat" type="button">×</button>
      </div>

      {error && <p className="process-error" role="alert">{error}</p>}
      {tabs.length ? tabs.map((tab) => (
        <section aria-label={`${tab.title} ekranı`} hidden={activeId !== tab.terminalId} id={`terminal-panel-${tab.terminalId}`} key={tab.terminalId} role="tabpanel">
          <XtermSession active={activeId === tab.terminalId} runtime={runtime} terminalId={tab.terminalId} />
        </section>
      )) : (
        <div className="terminal-tabs__empty">
          <Icon name="terminal" size={24} />
          <p>Bu çalışma alanında henüz terminal açılmadı.</p>
          <button disabled={opening} onClick={() => void openTerminal()} type="button">İlk terminali aç</button>
        </div>
      )}
    </div>
  );
}
