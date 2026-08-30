import { useState, type KeyboardEvent } from "react";
import type { ProtocolClient } from "../protocol/client";
import type { WorkspaceEntry } from "./types";
import { useWorkspace } from "./useWorkspace";
import "./FileExplorer.css";

interface FileExplorerProps {
  client: ProtocolClient;
  onChanged?: () => void;
  onSelected?: (path: string) => void;
  root: string;
}

export function FileExplorer({ client, onChanged, onSelected, root }: FileExplorerProps) {
  const { state, saveSelected, selectFile, toggleDirectory } = useWorkspace(client, root);
  const [editContent, setEditContent] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const moveTreeFocus = (event: KeyboardEvent<HTMLButtonElement>, target: number) => {
    const tree = event.currentTarget.closest('[role="tree"]');
    const items = Array.from(tree?.querySelectorAll<HTMLButtonElement>('[role="treeitem"]') ?? []);
    const current = items.indexOf(event.currentTarget);
    const index = target < 0 ? items.length - 1 : Math.min(target, items.length - 1);
    if (current >= 0 && items[index]) items[index].focus();
  };

  const renderEntries = (path: string, depth: number) => {
    const entries = state.directories[path] ?? [];
    return entries.map((entry: WorkspaceEntry) => {
      const folder = entry.tur === "klasor";
      const expanded = folder && state.expanded.has(entry.yol);
      return (
        <div className="file-explorer__branch" key={entry.yol}>
          <button
            aria-expanded={folder ? expanded : undefined}
            className="file-explorer__entry"
            onClick={() => {
              if (folder) void toggleDirectory(entry.yol);
              else {
                // Seçim değişikliğinin sonradan çalışan bir effect'i, kullanıcı
                // yeni dosyada hemen Düzenle'ye bastıktan sonra editörü kapatmasın.
                setEditContent(null);
                setSaveError(null);
                onSelected?.(entry.yol);
                void selectFile(entry.yol);
              }
            }}
            onKeyDown={(event) => {
              const tree = event.currentTarget.closest('[role="tree"]');
              const items = Array.from(
                tree?.querySelectorAll<HTMLButtonElement>('[role="treeitem"]') ?? [],
              );
              const current = items.indexOf(event.currentTarget);
              if (event.key === "ArrowDown") {
                event.preventDefault();
                moveTreeFocus(event, current + 1);
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                moveTreeFocus(event, Math.max(0, current - 1));
              } else if (event.key === "Home") {
                event.preventDefault();
                moveTreeFocus(event, 0);
              } else if (event.key === "End") {
                event.preventDefault();
                moveTreeFocus(event, -1);
              } else if (folder && event.key === "ArrowRight" && !expanded) {
                event.preventDefault();
                void toggleDirectory(entry.yol);
              } else if (folder && event.key === "ArrowLeft" && expanded) {
                event.preventDefault();
                void toggleDirectory(entry.yol);
              }
            }}
            role="treeitem"
            style={{ paddingInlineStart: 10 + depth * 16 }}
            title={entry.yol}
            type="button"
          >
            <span aria-hidden="true" className="file-explorer__chevron">
              {folder ? (expanded ? "⌄" : "›") : ""}
            </span>
            <span aria-hidden="true" className={`file-explorer__kind file-explorer__kind--${entry.tur}`} />
            <span className="file-explorer__name">{entry.ad}</span>
          </button>
          {expanded && (
            <div role="group">{renderEntries(entry.yol, depth + 1)}</div>
          )}
        </div>
      );
    });
  };

  return (
    <div className="file-explorer">
      <div aria-label="Proje dosyaları" className="file-explorer__tree" role="tree">
        {state.loading && Object.keys(state.directories).length === 0 ? (
          <p className="file-explorer__state">Dosyalar yükleniyor…</p>
        ) : state.error ? (
          <p className="file-explorer__state file-explorer__state--error" role="alert">{state.error}</p>
        ) : (state.directories[""]?.length ?? 0) === 0 ? (
          <p className="file-explorer__state">Bu proje klasörü boş.</p>
        ) : (
          renderEntries("", 0)
        )}
      </div>
      <div className="file-explorer__viewer">
        {state.selected ? (
          <>
            <div className="file-explorer__file-head">
              <div>
                <strong>{state.selected.yol}</strong>
                {state.selected.tur === "metin" && editContent === null && (
                  <button onClick={() => setEditContent(state.selected?.icerik ?? "")} type="button">
                    Düzenle
                  </button>
                )}
              </div>
              <span>{state.selected.mime} · {state.selected.boyut.toLocaleString("tr-TR")} bayt</span>
            </div>
            {state.selected.tur === "binary" ? (
              <p className="file-explorer__state">Bu dosya metin değil. Önizleme sekmesinden açılabilir.</p>
            ) : editContent !== null ? (
              <div className="file-explorer__editor">
                <textarea
                  aria-label="Dosya içeriği"
                  onChange={(event) => setEditContent(event.target.value)}
                  spellCheck={false}
                  value={editContent}
                />
                {saveError && <p role="alert">{saveError}</p>}
                <div className="file-explorer__editor-actions">
                  <button onClick={() => setEditContent(null)} type="button">Vazgeç</button>
                  <button
                    onClick={() => {
                      void saveSelected(editContent)
                        .then(() => {
                          setEditContent(null);
                          setSaveError(null);
                          onChanged?.();
                        })
                        .catch((reason) => setSaveError(String(reason)));
                    }}
                    type="button"
                  >
                    Kaydet
                  </button>
                </div>
              </div>
            ) : (
              <pre tabIndex={0}>
                <code>
                  {(state.selected.icerik ?? "").split("\n").map((line, index) => (
                    <span className="file-explorer__code-line" key={`${index}-${line}`}>
                      <span aria-hidden="true" className="file-explorer__line-number">
                        {index + 1}
                      </span>
                      <span>{line || " "}</span>
                    </span>
                  ))}
                </code>
              </pre>
            )}
            {state.selected.kesildi && (
              <p className="file-explorer__notice">Dosyanın yalnız ilk bölümü gösteriliyor.</p>
            )}
          </>
        ) : (
          <p className="file-explorer__state">İçeriğini görmek için bir dosya seç.</p>
        )}
      </div>
    </div>
  );
}
