import { useState } from 'react';
import type { Page } from '../../server/pages';
import type { PageDraft } from './autosave';
import { suggestPageMerge, type PageConflictSnapshot } from './page-conflict';
import './PageConflictPanel.css';

export function PageConflictPanel({
  snapshot,
  pages,
  onApply,
  onClose,
}: {
  snapshot: PageConflictSnapshot;
  pages: Page[];
  onApply: (draft: PageDraft) => void;
  onClose: () => void;
}) {
  const [suggestion] = useState(() => suggestPageMerge(snapshot));
  const [draft, setDraft] = useState(suggestion.draft);
  const [resolved, setResolved] = useState<Set<keyof PageDraft>>(
    () => new Set(),
  );
  const [acknowledged, setAcknowledged] = useState(false);
  const update = <K extends keyof PageDraft>(field: K, value: PageDraft[K]) => {
    setDraft((current) => ({ ...current, [field]: value }));
    setResolved((current) => new Set([...current, field]));
  };
  const unresolved = suggestion.conflicts.filter(
    (field) => !resolved.has(field),
  );
  const parentName = (id: string | null) =>
    id === null
      ? 'Alan kökü'
      : (pages.find((page) => page.id === id)?.title ?? 'Bilinmeyen üst sayfa');
  const choose = (field: keyof PageDraft) => (
    <div className="page-conflict-choices">
      <button
        type="button"
        onClick={() => update(field, snapshot.local[field])}
      >
        Yerel sürümü seç
      </button>
      <button
        type="button"
        onClick={() => update(field, snapshot.remote[field])}
      >
        Sunucu sürümünü seç
      </button>
    </div>
  );
  return (
    <section
      className="page-conflict-panel"
      aria-label="Sayfa sürümlerini karşılaştır"
    >
      <header>
        <h2>Sürümleri karşılaştır ve birleştir</h2>
        <button type="button" onClick={onClose}>
          Karşılaştırmayı kapat
        </button>
      </header>
      <p>
        Yerel taslağın korunuyor. Her iki tarafta değişen alanları seç veya
        birleşim metnini düzenle. Kaydetmeden önce sunucu sürümü tekrar
        doğrulanır.
      </p>
      <div className="page-conflict-versions">
        {[
          ['Yerel taslak', snapshot.local],
          [`Sunucudaki sürüm · r${snapshot.remoteRevision}`, snapshot.remote],
        ].map(([label, value]) => {
          const version = value as Readonly<PageDraft>;
          return (
            <article key={String(label)}>
              <h3>{String(label)}</h3>
              <strong>{version.title}</strong>
              <p>Üst sayfa: {parentName(version.parentId)}</p>
              <pre>{version.content}</pre>
            </article>
          );
        })}
      </div>
      <div className="page-conflict-merge">
        <h3>Kaydedilecek birleşim</h3>
        <label>
          Birleşim başlığı
          <input
            value={draft.title}
            maxLength={160}
            onChange={(event) => update('title', event.target.value)}
          />
        </label>
        {suggestion.conflicts.includes('title') && choose('title')}
        <label>
          Birleşim içeriği
          <textarea
            value={draft.content}
            maxLength={100000}
            rows={10}
            onChange={(event) => update('content', event.target.value)}
          />
        </label>
        {suggestion.conflicts.includes('content') && choose('content')}
        <label>
          Birleşimin üst sayfası
          <select
            value={draft.parentId ?? ''}
            onChange={(event) => update('parentId', event.target.value || null)}
          >
            <option value="">Alan kökü</option>
            {pages
              .filter((page) => page.id !== snapshot.pageId)
              .map((page) => (
                <option value={page.id} key={page.id}>
                  {page.title}
                </option>
              ))}
            {draft.parentId &&
              !pages.some((page) => page.id === draft.parentId) && (
                <option value={draft.parentId}>Bilinmeyen üst sayfa</option>
              )}
          </select>
        </label>
        {suggestion.conflicts.includes('parentId') && choose('parentId')}
        {unresolved.length > 0 && (
          <p role="status">
            Karar bekleyen alanlar:{' '}
            {unresolved
              .map(
                (field) =>
                  ({
                    title: 'başlık',
                    content: 'içerik',
                    parentId: 'üst sayfa',
                  })[field],
              )
              .join(', ')}
            .
          </p>
        )}
        <label className="page-conflict-ack">
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={(event) => setAcknowledged(event.target.checked)}
          />{' '}
          Birleşimi kontrol ettim; bu sürüm kaydedilsin.
        </label>
        <button
          type="button"
          disabled={
            unresolved.length > 0 || !acknowledged || !draft.title.trim()
          }
          onClick={() => onApply(draft)}
        >
          Birleşimi kaydet
        </button>
      </div>
    </section>
  );
}
