import { useEffect, useMemo, useRef, useState } from 'react';
import {
  FileText,
  Plus,
  Search,
  LayoutGrid,
  List,
  ArrowUpRight,
} from 'lucide-react';
import type { Page } from '../server/pages';
import type { Space } from '../shared/types';
export function pageExcerpt(content: string) {
  return content
    .replace(/^---\r?\n[\s\S]*?\r?\n---(?:\r?\n|$)/, '')
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/^\s*(?:[-+*]|\d+[.)])\s+(?:\[[ xX]\]\s+)?/gm, '')
    .replace(/```[\s\S]*?```/g, 'Kod bloğu')
    .replace(/!?\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/[#>*_`|~]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 150);
}
interface SpaceLibraryProps {
  space: Space;
  pages: Page[];
  onPage: (id: string) => void;
  onNew: () => void;
  pending?: boolean;
}
export function foldLibraryText(text: string): string {
  return text.normalize('NFKC').toLocaleLowerCase('tr-TR');
}
export function SpaceLibrary(props: SpaceLibraryProps) {
  return <LibraryContent key={props.space.id} {...props} />;
}
function LibraryContent({
  space,
  pages,
  onPage,
  onNew,
  pending = false,
}: SpaceLibraryProps) {
  const [query, setQuery] = useState('');
  const [layout, setLayout] = useState<'grid' | 'list'>('grid');
  const [sort, setSort] = useState('recent');
  const [visible, setVisible] = useState({ key: '', count: 50 });
  const filterKey = JSON.stringify([space.id, query, layout, sort]);
  const visibleCount = visible.key === filterKey ? visible.count : 50;
  const cards = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef<{ key: string; index: number } | null>(null);
  useEffect(() => {
    const pending = pendingFocus.current;
    if (!pending) return;
    pendingFocus.current = null;
    if (pending.key === filterKey && visibleCount > pending.index) {
      const newCard =
        cards.current?.querySelectorAll<HTMLButtonElement>(
          '.library-page-card',
        )[pending.index];
      newCard?.focus();
    }
  }, [filterKey, visibleCount]);
  const resetVisible = () => {
    pendingFocus.current = null;
    setVisible({ key: '', count: 50 });
  };
  const needle = foldLibraryText(query.trim());
  const filtered = useMemo(
    () =>
      pages
        .filter((page) =>
          foldLibraryText(`${page.title} ${page.content}`).includes(needle),
        )
        .sort((a, b) =>
          sort === 'name'
            ? a.title.localeCompare(b.title, 'tr-TR') ||
              a.id.localeCompare(b.id)
            : b.updatedAt - a.updatedAt ||
              a.title.localeCompare(b.title, 'tr-TR') ||
              a.id.localeCompare(b.id),
        ),
    [pages, needle, sort],
  );
  return (
    <section
      className="space-library"
      aria-label={`${space.name} sayfa kitaplığı`}
    >
      <header className="library-heading">
        <div>
          <span className="library-eyebrow">ALAN</span>
          <h1>{space.name}</h1>
          {space.description && <p>{space.description}</p>}
        </div>
        <button className="document-primary" onClick={onNew} disabled={pending}>
          <Plus size={17} /> Yeni sayfa
        </button>
      </header>
      <div className="library-tools">
        <label className="library-search">
          <Search size={17} />
          <input
            aria-label="Sayfalarda ara"
            placeholder="Sayfalarda ara"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              resetVisible();
            }}
          />
        </label>
        <label className="library-sort">
          <span className="sr-only">Sayfaları sırala</span>
          <select
            aria-label="Sayfaları sırala"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              resetVisible();
            }}
          >
            <option value="recent">Son düzenlenen</option>
            <option value="name">Ad A–Z</option>
          </select>
        </label>
        <div
          className="library-view-toggle"
          role="group"
          aria-label="Kitaplık görünümü"
        >
          <button
            aria-label="Izgara görünümü"
            aria-pressed={layout === 'grid'}
            onClick={() => {
              setLayout('grid');
              resetVisible();
            }}
          >
            <LayoutGrid size={17} />
          </button>
          <button
            aria-label="Liste görünümü"
            aria-pressed={layout === 'list'}
            onClick={() => {
              setLayout('list');
              resetVisible();
            }}
          >
            <List size={18} />
          </button>
        </div>
      </div>
      <div className="library-section-label">
        <h2>{query ? 'Arama sonuçları' : 'Tüm sayfalar'}</h2>
        <span>
          {filtered.length} {'sayfa'} ·{' '}
          {Math.min(visibleCount, filtered.length)} gösteriliyor
        </span>
      </div>
      {filtered.length ? (
        <>
          <div className={`library-pages ${layout}`} ref={cards}>
            {filtered.slice(0, visibleCount).map((page) => (
              <button
                className="library-page-card"
                key={page.id}
                onClick={() => onPage(page.id)}
              >
                <span className="library-page-icon">
                  <FileText size={20} strokeWidth={1.5} />
                </span>
                <div className="library-card-body">
                  <h3>{page.title}</h3>
                  <p>
                    {pageExcerpt(page.content) ||
                      'Boş bir sayfa, yazmaya hazır.'}
                  </p>
                  <div className="library-page-meta">
                    <span title={new Date(page.updatedAt).toLocaleString()}>
                      Düzenlendi{' '}
                      {new Date(page.updatedAt).toLocaleDateString('tr-TR', {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </span>
                    {page.parentId && (
                      <span className="library-parent">
                        {
                          pages.find((parent) => parent.id === page.parentId)
                            ?.title
                        }
                      </span>
                    )}
                  </div>
                </div>
                <ArrowUpRight className="library-card-arrow" size={15} />
              </button>
            ))}
          </div>
          {visibleCount < filtered.length && (
            <div className="library-load-more">
              <button
                className="document-primary"
                onClick={() => {
                  pendingFocus.current = {
                    key: filterKey,
                    index: visibleCount,
                  };
                  setVisible((previous) => ({
                    key: filterKey,
                    count:
                      (previous.key === filterKey ? previous.count : 50) + 50,
                  }));
                }}
              >
                {Math.min(50, filtered.length - visibleCount)} sayfa daha göster
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="library-empty">
          <FileText size={30} strokeWidth={1.3} />
          <h2>{query ? 'Eşleşen sayfa yok' : 'Henüz sayfa yok'}</h2>
          <p>
            {query
              ? 'Farklı bir başlık veya ifade dene.'
              : 'Bu Alan’ı düzenlemeye başlamak için ilk sayfanı oluştur.'}
          </p>
          {!query && (
            <button
              className="document-primary"
              onClick={onNew}
              disabled={pending}
            >
              <Plus size={16} /> Yeni sayfa
            </button>
          )}
        </div>
      )}
    </section>
  );
}
