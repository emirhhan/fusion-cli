import { useEffect, useId, useMemo, useRef, useState } from "react";
import { KIND_LABELS, parseQuery, rankItems, readRecent, rememberRecent, type PaletteItem } from "./paletteItems";
import "./CommandPalette.css";

/**
 * Global komut paleti (P-046): ⌘K her şeyi, ⌘P dosyaları arar.
 *
 * Claude Code / VS Code paleti örnek alınmıştır: tek giriş, klavyeyle gezilen tek liste,
 * önekle daraltma (`>` eylem, `/` komut, `@` dosya, `#` sohbet, `?` ayar). Boş sorguda son
 * kullanılanlar başta gelir (her yerden erişilen komut geçmişi). Dosya araması çekirdeğe
 * gider ve yazmayı bekletmez: son sorgunun cevabı kazanır.
 */

const FILE_DEBOUNCE_MS = 120;

interface CommandPaletteProps {
  initialQuery: string;
  items: readonly PaletteItem[];
  onClose: () => void;
  searchFiles?: (query: string) => Promise<PaletteItem[]>;
}

export function CommandPalette({ initialQuery, items, onClose, searchFiles }: CommandPaletteProps) {
  const [query, setQuery] = useState(initialQuery);
  const [activeIndex, setActiveIndex] = useState(0);
  const [files, setFiles] = useState<PaletteItem[]>([]);
  const [recent] = useState(readRecent);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const fileSequence = useRef(0);
  const listId = useId();

  useEffect(() => {
    const previous = document.activeElement;
    inputRef.current?.focus();
    inputRef.current?.setSelectionRange(initialQuery.length, initialQuery.length);
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus();
    };
    // Yalnız açılışta: sorgu değişince odak yeniden kurulmaz (palet sorgu başına `key` ile yeniden kurulur).
  }, []);

  const { text, kinds } = parseQuery(query);
  const wantsFiles = Boolean(searchFiles && text && (!kinds || kinds.includes("dosya")));
  useEffect(() => {
    const sequence = ++fileSequence.current;
    if (!wantsFiles || !searchFiles) { setFiles([]); return; }
    const timer = window.setTimeout(() => {
      void searchFiles(text).then(
        (found) => { if (sequence === fileSequence.current) setFiles(found); },
        () => { if (sequence === fileSequence.current) setFiles([]); },
      );
    }, FILE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [searchFiles, text, wantsFiles]);

  const results = useMemo(() => rankItems([...items, ...files], query, recent), [files, items, query, recent]);
  useEffect(() => setActiveIndex(0), [query]);
  const active = results[Math.min(activeIndex, results.length - 1)];
  useEffect(() => {
    const row = active ? listRef.current?.querySelector<HTMLElement>(`[data-id="${CSS.escape(active.id)}"]`) : null;
    row?.scrollIntoView?.({ block: "nearest" });
  }, [active]);

  const choose = (item: PaletteItem | undefined) => {
    if (!item) return;
    rememberRecent(item.id);
    onClose();
    item.run();
  };
  const onKeyDown = (event: React.KeyboardEvent) => {
    const count = results.length;
    if (event.key === "Escape") { event.preventDefault(); onClose(); }
    else if (event.key === "ArrowDown" && count) { event.preventDefault(); setActiveIndex((index) => (index + 1) % count); }
    else if (event.key === "ArrowUp" && count) { event.preventDefault(); setActiveIndex((index) => (index - 1 + count) % count); }
    else if (event.key === "Enter") { event.preventDefault(); choose(active); }
    else if (event.key === "Tab") event.preventDefault(); // Odak giriş kutusunda kalır.
  };
  const showRecentHeading = !text && !kinds && recent.length > 0;

  return (
    <div className="command-palette" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }} role="presentation">
      <section aria-label="Komut paleti" aria-modal="true" className="command-palette__panel" onKeyDown={onKeyDown} role="dialog">
        <div className="command-palette__field">
          <span aria-hidden="true" className="command-palette__glyph">⌕</span>
          <input
            aria-activedescendant={active ? `${listId}-${active.id}` : undefined}
            aria-autocomplete="list"
            aria-controls={listId}
            aria-expanded="true"
            aria-label="Komut, sohbet, dosya ya da ayar ara"
            className="command-palette__input"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ne yapmak istiyorsun?  > eylem  / komut  @ dosya  # sohbet  ? ayar"
            ref={inputRef}
            role="combobox"
            spellCheck={false}
            value={query}
          />
        </div>
        {showRecentHeading && <p className="command-palette__heading">Son kullanılanlar ve tümü</p>}
        <ul className="command-palette__list" id={listId} ref={listRef} role="listbox">
          {results.map((item) => (
            <li
              aria-selected={item === active}
              className="command-palette__option"
              data-id={item.id}
              id={`${listId}-${item.id}`}
              key={item.id}
              onClick={() => choose(item)}
              onMouseMove={() => { if (item !== active) setActiveIndex(results.indexOf(item)); }}
              role="option"
            >
              <span className="command-palette__kind" data-kind={item.kind}>{KIND_LABELS[item.kind]}</span>
              <span className="command-palette__label">{item.label}</span>
              {item.detail && <span className="command-palette__detail">{item.detail}</span>}
              {item.shortcut && <kbd className="command-palette__kbd">{item.shortcut}</kbd>}
            </li>
          ))}
        </ul>
        {results.length === 0 && (
          <p className="command-palette__empty" role="status">
            {wantsFiles ? "Eşleşen bir şey yok (dosyalar aranıyor olabilir)." : "Eşleşen bir şey yok."}
          </p>
        )}
        <footer className="command-palette__footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> gez</span>
          <span><kbd>↩</kbd> aç</span>
          <span><kbd>Esc</kbd> kapat</span>
        </footer>
      </section>
    </div>
  );
}
