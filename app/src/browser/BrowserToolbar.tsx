import { useEffect, useRef } from "react";
import { BROWSER_VIEWPORTS } from "./browserPanelProtocol";

/** Cmd/Ctrl+Shift+S: öğe seçiciyi aç/kapat (Claude Code Desktop Browser bölmesi, #444). */
export function isPickShortcut(event: KeyboardEvent): boolean {
  return (event.metaKey || event.ctrlKey) && event.shiftKey && !event.altKey && (event.code === "KeyS" || event.key.toLowerCase() === "s");
}

/** Tarayıcı panelinin araç çubuğu: gezinme, adres, görünüm, öğe seçici, görüntü, konsol. */
export interface BrowserToolbarProps {
  address: string;
  busy: boolean;
  isOpen: boolean;
  picking: boolean;
  consoleOpen: boolean;
  viewportId: string;
  onAddressChange: (value: string) => void;
  onSubmit: () => void;
  onHistory: (step: "geri" | "ileri" | "yenile") => void;
  onViewport: (id: string) => void;
  onPickToggle: () => void;
  onScreenshot: () => void;
  onConsole: () => void;
}

export function BrowserToolbar({
  address, busy, isOpen, picking, consoleOpen, viewportId,
  onAddressChange, onSubmit, onHistory, onViewport, onPickToggle, onScreenshot, onConsole,
}: BrowserToolbarProps) {
  const pickRef = useRef(onPickToggle);
  pickRef.current = onPickToggle;
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || !isPickShortcut(event)) return;
      event.preventDefault();
      pickRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isOpen]);
  return (
    <div className="browser-toolbar">
      <div className="browser-toolbar__nav">
        <button aria-label="Geri" disabled={!isOpen} onClick={() => onHistory("geri")} title="Geri" type="button">‹</button>
        <button aria-label="İleri" disabled={!isOpen} onClick={() => onHistory("ileri")} title="İleri" type="button">›</button>
        <button aria-label="Yenile" disabled={!isOpen} onClick={() => onHistory("yenile")} title="Yenile" type="button">↻</button>
      </div>
      <form onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
        <label className="browser-panel__sr-only" htmlFor="browser-address">Tarayıcı adresi</label>
        <input
          id="browser-address"
          onChange={(event) => onAddressChange(event.target.value)}
          placeholder="Adres ya da localhost:5173"
          spellCheck={false}
          value={address}
        />
        <button aria-label="Adrese git" disabled={busy} type="submit">{isOpen ? "Git" : "Aç"}</button>
      </form>
      <select aria-label="Sayfa boyutu" disabled={!isOpen} onChange={(event) => onViewport(event.target.value)} value={viewportId}>
        {BROWSER_VIEWPORTS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select>
      <div className="browser-toolbar__actions">
        <button
          aria-label="Öğe seç ve sohbete ekle"
          aria-pressed={picking}
          disabled={!isOpen}
          onClick={onPickToggle}
          title="Öğe seç (⌘⇧S): tıkladığın öğenin seçicisi ve görüntüsü sohbete eklenir"
          type="button"
        >⌖</button>
        <button aria-label="Görüntüyü sohbete ekle" disabled={!isOpen} onClick={onScreenshot} title="Görüntüyü sohbete ekle" type="button">◧</button>
        <button aria-label="Konsol ve ağ" aria-pressed={consoleOpen} disabled={!isOpen} onClick={onConsole} title="Konsol ve ağ" type="button">≡</button>
      </div>
    </div>
  );
}
