import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "../ui/Icon";
import type { ProjectProcess, ProcessStatus } from "./types";
import type { ProcessController, ProcessOutputStream } from "./useProcesses";

const statusLabels: Record<ProcessStatus, string> = {
  bitti: "Bitti",
  calisiyor: "Çalışıyor",
  durduruldu: "Durduruldu",
  hata: "Hata",
};

export function stripAnsi(value: string): string {
  return value
    .replace(/(?:\u001B\]|\u009D)[\s\S]*?(?:\u0007|\u001B\\|\u009C|$)/g, "")
    .replace(/(?:\u001B\[|\u009B)[0-?]*[ -/]*[@-~]/g, "")
    .replace(/\u001B[@-_]/g, "");
}

interface ClearMarker {
  snapshot: string;
  streamTotal: number;
}

function outputSinceClear(marker: ClearMarker | undefined, current: string, stream: ProcessOutputStream | undefined): string {
  if (!marker) return current;
  if (stream && stream.total > marker.streamTotal) {
    const added = stream.total - marker.streamTotal;
    return stream.text.slice(-Math.min(added, stream.text.length));
  }
  return outputAfterClear(marker.snapshot, current);
}

export function outputAfterClear(clearedSnapshot: string | undefined, current: string): string {
  if (clearedSnapshot === undefined) return current;
  if (current.startsWith(clearedSnapshot)) return current.slice(clearedSnapshot.length);
  if (!current || !clearedSnapshot) return current;

  // Backend çıktıyı sabit boyutlu dönen tamponda tutar. Tampon dolunca uzunluk
  // değişmez; eski snapshot'ın sonu ile yeni snapshot'ın başındaki en uzun
  // örtüşmeyi KMP ile O(n) bulup yalnız yeni son eki gösteririz.
  const prefix = new Array<number>(current.length).fill(0);
  for (let index = 1, matched = 0; index < current.length; index += 1) {
    while (matched > 0 && current[index] !== current[matched]) matched = prefix[matched - 1];
    if (current[index] === current[matched]) matched += 1;
    prefix[index] = matched;
  }
  let overlap = 0;
  for (let index = 0; index < clearedSnapshot.length; index += 1) {
    while (overlap > 0 && clearedSnapshot[index] !== current[overlap]) overlap = prefix[overlap - 1];
    if (clearedSnapshot[index] === current[overlap]) overlap += 1;
    if (overlap === current.length && index < clearedSnapshot.length - 1) overlap = prefix[overlap - 1];
  }
  return current.slice(overlap);
}

function latestProcess(processes: ProjectProcess[]): ProjectProcess | null {
  return processes.reduce<ProjectProcess | null>(
    (latest, process) => !latest || process.baslangic >= latest.baslangic ? process : latest,
    null,
  );
}

export function TerminalTabs({ controller }: { controller: ProcessController }) {
  const [activeId, setActiveId] = useState(() => latestProcess(controller.processes)?.surec_id ?? null);
  const [closedIds, setClosedIds] = useState<Set<string>>(() => new Set());
  const [clearMarkers, setClearMarkers] = useState<Record<string, ClearMarker>>({});
  const [command, setCommand] = useState("");
  const [copyError, setCopyError] = useState<string | null>(null);
  const commandInputRef = useRef<HTMLInputElement>(null);
  const outputRef = useRef<HTMLDivElement>(null);
  const knownIds = useRef(new Set(controller.processes.map((process) => process.surec_id)));

  const visibleProcesses = useMemo(
    () => controller.processes.filter((process) => !closedIds.has(process.surec_id)),
    [closedIds, controller.processes],
  );
  const active = visibleProcesses.find((process) => process.surec_id === activeId)
    ?? latestProcess(visibleProcesses);
  const rawOutput = active?.cikti ?? "";
  const output = active
    ? stripAnsi(outputSinceClear(clearMarkers[active.surec_id], rawOutput, controller.outputStreams?.[active.surec_id]))
    : "";

  useEffect(() => {
    const incoming = controller.processes.filter((process) => !knownIds.current.has(process.surec_id));
    knownIds.current = new Set(controller.processes.map((process) => process.surec_id));
    const newest = latestProcess(incoming);
    if (newest) {
      setClosedIds((current) => {
        if (!current.has(newest.surec_id)) return current;
        const next = new Set(current);
        next.delete(newest.surec_id);
        return next;
      });
      setActiveId(newest.surec_id);
    }
  }, [controller.processes]);

  useEffect(() => {
    if (activeId && visibleProcesses.some((process) => process.surec_id === activeId)) return;
    setActiveId(latestProcess(visibleProcesses)?.surec_id ?? null);
  }, [activeId, visibleProcesses]);

  useEffect(() => {
    const node = outputRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [active?.surec_id, output]);

  const closeActive = () => {
    if (!active || active.durum === "calisiyor") return;
    setClosedIds((current) => new Set(current).add(active.surec_id));
  };
  const clearActive = () => {
    if (!active) return;
    setClearMarkers((current) => ({
      ...current,
      [active.surec_id]: {
        snapshot: active.cikti,
        streamTotal: controller.outputStreams?.[active.surec_id]?.total ?? 0,
      },
    }));
  };
  const copyActive = async () => {
    if (!active) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Pano kullanılamıyor");
      await navigator.clipboard.writeText(output);
      setCopyError(null);
    } catch {
      setCopyError("Terminal çıktısı panoya kopyalanamadı.");
    }
  };
  const selectRelativeTab = (currentIndex: number, direction: number) => {
    if (visibleProcesses.length === 0) return;
    const nextIndex = (currentIndex + direction + visibleProcesses.length) % visibleProcesses.length;
    const next = visibleProcesses[nextIndex];
    setActiveId(next.surec_id);
    window.requestAnimationFrame(() => {
      document.getElementById(`terminal-tab-${next.surec_id}`)?.focus();
    });
  };

  return (
    <div className="terminal-tabs">
      <div className="terminal-tabs__strip">
        <div aria-label="Terminal oturumları" className="terminal-tabs__list" role="tablist">
          {visibleProcesses.map((process, index) => (
            <button
              aria-controls={active?.surec_id === process.surec_id ? "active-terminal-panel" : undefined}
              aria-label={`${process.komut} terminali`}
              aria-selected={active?.surec_id === process.surec_id}
              className="terminal-tabs__tab"
              id={`terminal-tab-${process.surec_id}`}
              key={process.surec_id}
              onClick={() => setActiveId(process.surec_id)}
              onKeyDown={(event) => {
                if (event.key === "ArrowLeft") {
                  event.preventDefault();
                  selectRelativeTab(index, -1);
                } else if (event.key === "ArrowRight") {
                  event.preventDefault();
                  selectRelativeTab(index, 1);
                } else if (event.key === "Home") {
                  event.preventDefault();
                  selectRelativeTab(0, 0);
                } else if (event.key === "End") {
                  event.preventDefault();
                  selectRelativeTab(visibleProcesses.length - 1, 0);
                }
              }}
              role="tab"
              tabIndex={active?.surec_id === process.surec_id ? 0 : -1}
              title={`${process.cwd} · ${statusLabels[process.durum]}`}
              type="button"
            >
              <span className={`terminal-tabs__dot terminal-tabs__dot--${process.durum}`} />
              <span>{process.komut}</span>
            </button>
          ))}
        </div>
        <button
          aria-label="Yeni terminal"
          className="terminal-tabs__new"
          onClick={() => commandInputRef.current?.focus()}
          title="Yeni terminal"
          type="button"
        >
          <Icon name="new" size={16} />
        </button>
      </div>

      {controller.error && <p className="process-error" role="alert">{controller.error}</p>}
      {copyError && <p className="process-error" role="alert">{copyError}</p>}

      {active ? (
        <section
          aria-label={`${active.komut} terminali`}
          className="terminal-tabs__panel"
          id="active-terminal-panel"
          role="tabpanel"
        >
          <header className="terminal-tabs__toolbar">
            <div>
              <strong>{active.komut}</strong>
              <span>{active.cwd || "."}</span>
            </div>
            <span className={`terminal-tabs__status terminal-tabs__status--${active.durum}`}>
              {statusLabels[active.durum]}
              {active.cikis_kodu === null ? "" : ` · ${active.cikis_kodu}`}
            </span>
            <div className="terminal-tabs__actions">
              <button aria-label="Çıktıyı temizle" onClick={clearActive} title="Temizle" type="button">Temizle</button>
              <button aria-label="Çıktıyı kopyala" onClick={() => void copyActive()} title="Kopyala" type="button"><Icon name="copy" size={15} /></button>
              {active.durum === "calisiyor" ? (
                <button aria-label="Süreci durdur" onClick={() => void controller.stop(active.surec_id)} title="Durdur" type="button"><Icon name="stop" size={15} /></button>
              ) : (
                <>
                  <button aria-label="Yeniden çalıştır" onClick={() => void controller.start(active.komut, active.cwd)} title="Yeniden çalıştır" type="button">↻</button>
                  <button aria-label="Terminal sekmesini kapat" onClick={closeActive} title="Kapat" type="button">×</button>
                </>
              )}
            </div>
          </header>
          <div
            aria-label="Terminal çıktısı"
            aria-live="polite"
            className="terminal-tabs__output"
            ref={outputRef}
            role="log"
          >
            <pre>{output || (active.durum === "calisiyor" ? "Çalışıyor…" : "(çıktı yok)")}</pre>
          </div>
        </section>
      ) : (
        <div className="terminal-tabs__empty">
          <Icon name="terminal" size={24} />
          <p>Bu görevde henüz terminal açılmadı.</p>
          <button onClick={() => commandInputRef.current?.focus()} type="button">İlk terminali aç</button>
        </div>
      )}

      <form
        className="terminal-tabs__composer"
        onSubmit={(event) => {
          event.preventDefault();
          const next = command.trim();
          if (!next) return;
          void controller.start(next).then((started) => {
            if (started) setCommand("");
          });
        }}
      >
        <span aria-hidden="true">$</span>
        <input
          aria-label="Terminal komutu"
          autoCapitalize="off"
          autoComplete="off"
          onChange={(event) => setCommand(event.target.value)}
          placeholder="npm test"
          ref={commandInputRef}
          spellCheck={false}
          value={command}
        />
        <button disabled={controller.busy || !command.trim()} type="submit">Çalıştır</button>
      </form>
    </div>
  );
}
