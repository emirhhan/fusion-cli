import { useEffect, useRef, useState } from "react";
import { Icon } from "../ui/Icon";
import { XtermSession } from "./XtermSession";
import { terminalRuntime, type TerminalClosedEvent, type TerminalRuntime, type TerminalSession } from "./terminalBridge";

/** Ölçüm yapılamazsa kullanılan güvenli varsayılan. */
const VARSAYILAN_SUTUN = 80;
const VARSAYILAN_SATIR = 24;

/* Terminal yazı tipinin yaklaşık hücre boyutu. Kesin ölçüm xterm'in kendi
   `fit` eklentisinden gelir ve açılıştan hemen sonra çekirdeğe bildirilir;
   buradaki tahmin yalnız kabuğun İLK istemini doğru genişlikte çizmesi
   içindir. */
const HUCRE_GENISLIGI_PX = 8.4;
const HUCRE_YUKSEKLIGI_PX = 18;

interface TerminalTab {
  title: string;
  session: TerminalSession;
  closed: TerminalClosedEvent | null;
  stopClosed: () => void;
}

function closedStatus(closed: TerminalClosedEvent | null) {
  if (!closed) return { label: "Çalışıyor", tone: "calisiyor" };
  if (closed.exitCode === null) return { label: "Durduruldu", tone: "durduruldu" };
  if (closed.exitCode === 0) return { label: "Bitti", tone: "bitti" };
  return { label: `Hata (${closed.exitCode})`, tone: "hata" };
}

export function TerminalTabs({ cwd, runtime = terminalRuntime }: { cwd: string; runtime?: TerminalRuntime }) {
  const [tabs, setTabs] = useState<TerminalTab[]>([]);
  const tabsRef = useRef<TerminalTab[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);
  const nextNumber = useRef(1);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mountedRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      const owned = tabsRef.current;
      tabsRef.current = [];
      owned.forEach((tab) => {
        tab.stopClosed();
        if (tab.closed === null) void tab.session.close().finally(() => tab.session.dispose());
        else tab.session.dispose();
      });
    };
  }, []);

  /** Panelin gerçek sütun/satır sayısı; ölçülemezse güvenli varsayılan. */
  const olcVeyaVarsayilan = (): { cols: number; rows: number } => {
    const host = hostRef.current;
    if (!host) return { cols: VARSAYILAN_SUTUN, rows: VARSAYILAN_SATIR };
    const { width, height } = host.getBoundingClientRect();
    if (width <= 0 || height <= 0) return { cols: VARSAYILAN_SUTUN, rows: VARSAYILAN_SATIR };
    const cols = Math.max(20, Math.floor(width / HUCRE_GENISLIGI_PX));
    const rows = Math.max(5, Math.floor(height / HUCRE_YUKSEKLIGI_PX));
    return { cols, rows };
  };

  const openTerminal = async () => {
    if (opening) return;
    setOpening(true);
    setError(null);
    try {
      // Kabuk GERÇEK ölçüyle başlatılır. Sabit 80×24 ile açmak, kabuğun ilk
      // istemini ve tamamlama listesini 80 sütuna göre çizmesine yol açıyordu;
      // panel daha darsa satırlar yanlış yerde kayıyor ve tamamlama bozuk
      // görünüyordu (ölçüldü: "Appl" sağda kalıp "ications/" alt satıra düştü).
      const { cols, rows } = olcVeyaVarsayilan();
      const session = await runtime.openSession(cwd, cols, rows);
      if (!mountedRef.current) {
        await session.close().finally(() => session.dispose());
        return;
      }
      const tab: TerminalTab = {
        session,
        title: `Terminal ${nextNumber.current++}`,
        closed: null,
        stopClosed: () => undefined,
      };
      tab.stopClosed = session.onClosed((closed) => {
        tab.closed = closed;
        setTabs((current) => current.map((item) => item === tab ? { ...item, closed } : item));
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
      if (tab.closed === null) await tab.session.close();
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
    <div className="terminal-tabs" ref={hostRef}>
      <div className="terminal-tabs__strip">
        <div aria-label="Terminal oturumları" className="terminal-tabs__list" role="tablist">
          {tabs.map((tab, index) => {
            const { terminalId, cwd: terminalCwd, pid } = tab.session.snapshot;
            const status = closedStatus(tab.closed);
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
                title={`${terminalCwd} · ${tab.closed ? `${status.label}: ${tab.closed.reason}` : `PID ${pid ?? "—"}`}`}
                type="button"
              >
                <span className={`terminal-tabs__dot terminal-tabs__dot--${status.tone}`} />
                <span>{tab.title}</span>
                {tab.closed && <span className="terminal-tabs__state">{status.label}</span>}
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
            <XtermSession active={activeId === terminalId} closed={tab.closed} session={tab.session} />
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
