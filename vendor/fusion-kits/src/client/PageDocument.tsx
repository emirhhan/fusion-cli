import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  ArrowLeft,
  PanelLeft,
  Check,
  LoaderCircle,
  FileCode2,
} from 'lucide-react';
import type { Page } from '../server/pages';
import type { WorkspaceState } from '../shared/types';
import { api } from './api';
import { usePageAutosave } from './editor/use-page-autosave';
import { inspectMarkdown } from './editor/markdown';
import { DocumentMenu } from './editor/DocumentMenu';
import { PageConversation } from './PageConversation';
import { PageConflictPanel } from './editor/PageConflictPanel';
import type { PageConflictSnapshot } from './editor/page-conflict';
import type { PageDraft } from './editor/autosave';
import { AssetAttachments } from './AssetAttachments';
const RichEditor = lazy(() => import('./editor/RichEditor'));
export function PageDocument({
  page,
  pages,
  workspace,
  paused,
  onHome,
  onOutline,
  onSubpage,
  onDirty,
  onSaved,
  onRefresh,
  onSchedule,
  onThread,
  onSettings,
  onCreateDot,
}: {
  page: Page;
  pages: Page[];
  workspace: WorkspaceState;
  paused: boolean;
  onHome: () => void;
  onOutline: () => void;
  onSubpage: () => void;
  onDirty: (value: boolean) => void;
  onSaved: (page: Page) => void;
  onRefresh: () => void;
  onSchedule: (id: string) => void;
  onThread: (id: string) => void;
  onSettings: () => void;
  onCreateDot: () => void;
}) {
  const { controller, state } = usePageAutosave(
    page,
    onSaved,
    workspace.ownerId,
  );
  const draft = state.draft!;
  const [source, setSource] = useState(false);
  const [move, setMove] = useState(false);
  const [notice, setNotice] = useState('');
  const [chatOpen, setChatOpen] = useState(false);
  const [conflictPreview, setConflictPreview] =
    useState<PageConflictSnapshot | null>(null);
  const [latestLoading, setLatestLoading] = useState(false);
  const [comparisonGeneration, setComparisonGeneration] = useState(0);
  const latestRequest = useRef<AbortController | null>(null);
  const ownerScope = useRef('');
  ownerScope.current = JSON.stringify([page.spaceId, page.id]);
  useEffect(() => {
    setConflictPreview(null);
    setLatestLoading(false);
    setNotice('');
    return () => {
      latestRequest.current?.abort();
      latestRequest.current = null;
    };
  }, [page.spaceId, page.id]);
  const safety = useMemo(() => inspectMarkdown(draft.content), [draft.content]);
  const sourceMode = source || !safety.supported;
  useEffect(() => {
    onDirty(controller.dirty);
    return () => onDirty(false);
  }, [state, controller, onDirty]);
  useEffect(() => {
    const leave = (event: BeforeUnloadEvent) => {
      if (controller.dirty) event.preventDefault();
    };
    const save = (event: KeyboardEvent) => {
      if (
        (event.metaKey || event.ctrlKey) &&
        event.key.toLowerCase() === 's' &&
        !event.isComposing
      ) {
        event.preventDefault();
        void controller.flush(true);
      }
    };
    window.addEventListener('beforeunload', leave);
    window.addEventListener('keydown', save);
    return () => {
      window.removeEventListener('beforeunload', leave);
      window.removeEventListener('keydown', save);
    };
  }, [controller]);
  const beforeChat = useCallback(() => controller.flush(true), [controller]);
  const download = () => {
    const url = URL.createObjectURL(
      new Blob([draft.content], { type: 'text/markdown;charset=utf-8' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `${draft.title.replace(/[^\p{L}\p{N} -]/gu, '').slice(0, 80) || 'page'}.md`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const latest = async (compare = false) => {
    if (latestRequest.current) return;
    if (
      !compare &&
      !window.confirm(
        'Son kaydedilen sayfa yüklensin ve bu taslağın yerine geçsin mi? Taslağı saklamak istiyorsan önce indir.',
      )
    )
      return;
    const original = controller.getSnapshot().draft;
    if (!original) return;
    const scope = ownerScope.current;
    const operation = new AbortController();
    latestRequest.current = operation;
    setLatestLoading(true);
    const owns = () =>
      latestRequest.current === operation && ownerScope.current === scope;
    try {
      const remote = await api<Page>(
        `/spaces/${page.spaceId}/pages/${page.id}`,
        'GET',
        undefined,
        operation.signal,
      );
      if (!owns()) return;
      if (!controller.observeRemote(remote, original, page)) {
        setNotice(
          'Beklerken sayfa veya taslak değişti. Yeni yazdıkların korundu; son sürümü yeniden kontrol et.',
        );
        return;
      }
      if (compare) {
        const snapshot = controller.conflictSnapshot();
        setComparisonGeneration((current) => current + 1);
        setConflictPreview(snapshot);
        if (!snapshot) {
          setNotice(
            'Karşılaştırılacak yeni sunucu sürümü bulunamadı; taslak korundu.',
          );
          return;
        }
      } else {
        controller.useLatest();
        setConflictPreview(null);
      }
      setNotice('');
    } catch (error) {
      if (!owns()) return;
      setNotice(
        error instanceof Error
          ? error.message
          : 'Son sayfa yüklenemedi. Taslağın değişmedi.',
      );
    } finally {
      if (owns()) {
        latestRequest.current = null;
        setLatestLoading(false);
      }
    }
  };
  const applyMerge = async (merged: PageDraft) => {
    if (!conflictPreview) return;
    if (!controller.resolveConflict(conflictPreview, merged)) {
      setNotice(
        'İnceleme sırasında sayfa veya taslak değişti. Birleşim kaydedilmedi; karşılaştırmayı yeniden aç.',
      );
      return;
    }
    const scope = ownerScope.current;
    setConflictPreview(null);
    const saved = await controller.flush(true);
    if (ownerScope.current === scope)
      setNotice(
        saved
          ? 'Birleşim güncel sürüm kontrolüyle kaydedildi.'
          : 'Birleşim taslakta korundu; kayıt durumunu kontrol et.',
      );
  };
  const descendants = new Set([page.id]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const item of pages)
      if (
        item.parentId &&
        descendants.has(item.parentId) &&
        !descendants.has(item.id)
      ) {
        descendants.add(item.id);
        changed = true;
      }
  }
  const status =
    state.status === 'saving'
      ? 'Kaydediliyor…'
      : state.status === 'saved'
        ? 'Tüm değişiklikler kaydedildi'
        : state.status === 'dirty'
          ? 'Kaydedilmemiş değişiklikler'
          : state.status === 'conflict'
            ? 'Değişikliklerin gözden geçirilmesi gerekiyor'
            : 'Kaydedilemedi';
  return (
    <section
      className={`document-session ${chatOpen ? 'chat-visible' : ''}`}
      aria-label="Belge çalışma alanı"
    >
      <div className="document-column">
        <header className="document-topbar">
          <button className="document-back" onClick={onHome}>
            <ArrowLeft size={16} />
            <span>Tüm sayfalar</span>
          </button>
          <button
            className="document-icon"
            aria-label="Sayfa taslağını aç/kapat"
            onClick={onOutline}
          >
            <PanelLeft size={17} />
          </button>
          <span
            className={`document-save-status ${state.status}`}
            role="status"
            aria-live="polite"
          >
            {state.status === 'saved' ? (
              <Check size={13} />
            ) : state.status === 'saving' ? (
              <LoaderCircle size={13} className="saving-spinner" />
            ) : null}
            {status}
          </span>
          <DocumentMenu
            items={[
              {
                label: 'Şimdi kaydet · ⌘/Ctrl S',
                action: () => void controller.flush(true),
              },
              {
                label: sourceMode ? 'Görsel düzenleyici' : 'Markdown kaynağı',
                action: () => {
                  if (sourceMode && !safety.supported) {
                    setNotice(
                      safety.reason ?? 'Bu belge kaynak kipini gerektiriyor.',
                    );
                    return;
                  }
                  setSource(!sourceMode);
                },
              },
              { label: 'Sayfayı taşı', action: () => setMove(!move) },
              { label: 'Yeni alt sayfa', action: onSubpage },
              { label: 'Markdown indir', action: download },
              ...(page.sourceThreadId
                ? [
                    {
                      label: 'Kaynak sohbeti aç',
                      action: () => onThread(page.sourceThreadId!),
                    },
                  ]
                : []),
            ]}
          />
        </header>
        <div className="document-scroll">
          <article className="document-reading-column">
            {state.storageError && <p role="alert">{state.storageError}</p>}
            {state.error && (
              <div
                className={`document-save-notice ${state.status}`}
                role="alert"
              >
                <p>{state.error}</p>
                <div>
                  {state.status === 'error' && (
                    <button onClick={() => void controller.flush(true)}>
                      Kaydetmeyi yeniden dene
                    </button>
                  )}
                  <button onClick={download}>Taslağı indir</button>
                  {state.status === 'conflict' && (
                    <>
                      <button
                        disabled={latestLoading}
                        onClick={() => void latest(true)}
                      >
                        Karşılaştır ve birleştir
                      </button>
                      <button
                        disabled={latestLoading}
                        onClick={() => void latest()}
                      >
                        Sonuncuyu yükle
                      </button>
                    </>
                  )}
                </div>
              </div>
            )}
            {conflictPreview && (
              <PageConflictPanel
                key={`${conflictPreview.pageId}:${conflictPreview.remoteRevision}:${comparisonGeneration}`}
                snapshot={conflictPreview}
                pages={pages}
                onApply={(merged) => {
                  void applyMerge(merged);
                }}
                onClose={() => setConflictPreview(null)}
              />
            )}
            {notice && (
              <div className="document-notice" role="status">
                {notice}
                <button onClick={() => setNotice('')}>Kapat</button>
              </div>
            )}
            {move && (
              <div
                className="document-move"
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setMove(false);
                }}
              >
                <label>
                  Şunun altına taşı
                  <select
                    autoFocus
                    aria-label="Üst sayfa"
                    value={draft.parentId ?? ''}
                    onChange={(e) =>
                      controller.edit({ parentId: e.target.value || null })
                    }
                  >
                    <option value="">Alan kökü</option>
                    {pages
                      .filter((p) => !descendants.has(p.id))
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.title}
                        </option>
                      ))}
                  </select>
                </label>
                <button onClick={() => setMove(false)}>Bitti</button>
              </div>
            )}
            <input
              disabled={state.draftLoading}
              className="document-title"
              aria-label="Sayfa başlığı"
              placeholder="Başlıksız sayfa"
              maxLength={160}
              value={draft.title}
              onChange={(event) =>
                controller.edit({ title: event.target.value })
              }
            />
            {state.draftLoading ? (
              <p role="status">Yerel taslak kontrol ediliyor…</p>
            ) : sourceMode ? (
              <>
                <div className="source-mode-label">
                  <FileCode2 size={15} />
                  <span>Markdown kaynağı</span>
                </div>
                {!safety.supported && (
                  <p className="source-mode-reason">{safety.reason}</p>
                )}
                <textarea
                  className="document-source"
                  aria-label="Sayfa Markdown içeriği"
                  spellCheck={false}
                  value={draft.content}
                  maxLength={100000}
                  onChange={(event) =>
                    controller.edit({ content: event.target.value })
                  }
                />
              </>
            ) : (
              <Suspense
                fallback={
                  <div className="editor-loading">Düzenleyici yükleniyor…</div>
                }
              >
                <RichEditor
                  value={draft.content}
                  onChange={(content) => controller.edit({ content })}
                  onNotice={setNotice}
                />
              </Suspense>
            )}
            <AssetAttachments
              scope={JSON.stringify([workspace.ownerId, page.spaceId, page.id])}
              content={draft.content}
              onInsert={(markdown) => {
                const current = controller.getSnapshot().draft;
                if (!current) return;
                const content = `${current.content.trimEnd()}\n\n${markdown}\n`;
                if (content.length > 100000) {
                  setNotice('Belgenin boyut sınırı doldu; görsel eklenmedi.');
                  return;
                }
                controller.edit({ content });
              }}
            />
          </article>
        </div>
      </div>
      <div className={`document-assistant ${chatOpen ? 'open' : ''}`}>
        <PageConversation
          page={page}
          workspace={workspace}
          paused={paused}
          beforeChat={beforeChat}
          onRefresh={onRefresh}
          onSchedule={onSchedule}
          onSettings={onSettings}
          onCreateDot={onCreateDot}
          onOpenChange={setChatOpen}
        />
      </div>
    </section>
  );
}
