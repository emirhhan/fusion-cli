import { mergePageSnapshot } from './page-snapshots';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Page } from '../server/pages';
import type { Space, WorkspaceState } from '../shared/types';
import { api, errorText } from './api';
import { SpaceLibrary } from './SpaceLibrary';
import { PageDocument } from './PageDocument';
import { PageOutline } from './PageOutline';
export function SpaceWorkspace({
  space,
  pageId,
  workspace,
  paused,
  onPage,
  onDirty,
  onRefresh,
  onSchedule,
  onThread,
  onSettings,
  onCreateDot,
}: {
  space: Space;
  pageId?: string;
  workspace: WorkspaceState;
  paused: boolean;
  onPage: (id?: string) => void;
  onDirty: (value: boolean) => void;
  onRefresh: () => void;
  onSchedule: (threadId: string) => void;
  onThread: (threadId: string) => void;
  onSettings: () => void;
  onCreateDot: () => void;
}) {
  const [pages, setPages] = useState<Page[]>([]);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [outline, setOutline] = useState(false);
  const createOwner = useRef<{
    spaceId: string;
    active: boolean;
    pending: boolean;
    controller?: AbortController;
  }>({ spaceId: space.id, active: true, pending: false });
  const [creating, setCreating] = useState<{
    spaceId: string;
    pending: boolean;
  }>({ spaceId: space.id, pending: false });
  const createPending = creating.spaceId === space.id && creating.pending;
  useEffect(() => {
    let active = true;
    let inFlight = false;
    let controller: AbortController | undefined;
    const owner = {
      spaceId: space.id,
      active: true,
      pending: false,
      controller: undefined as AbortController | undefined,
    };
    createOwner.current = owner;
    const load = async () => {
      if (!active || inFlight || document.visibilityState === 'hidden') return;
      inFlight = true;
      const request = new AbortController();
      controller = request;
      try {
        const next = await api<Page[]>(
          `/spaces/${space.id}/pages`,
          'GET',
          undefined,
          request.signal,
        );
        if (active) {
          setPages((previous) => mergePageSnapshot(previous, next));
          setLoaded(true);
          setError('');
        }
      } catch (e) {
        if (active && !request.signal.aborted)
          setError(e instanceof Error ? e.message : 'Sayfalar yüklenemedi.');
      } finally {
        inFlight = false;
      }
    };
    const visibility = () => {
      if (document.visibilityState === 'visible') void load();
    };
    document.addEventListener('visibilitychange', visibility);
    void load();
    const timer = setInterval(() => void load(), 3000);
    return () => {
      active = false;
      owner.active = false;
      owner.controller?.abort();
      controller?.abort();
      document.removeEventListener('visibilitychange', visibility);
      clearInterval(timer);
    };
  }, [space.id]);
  const page = pages.find((item) => item.id === pageId);
  const saved = useCallback(
    (next: Page) =>
      setPages((previous) =>
        previous.map((item) =>
          item.id === next.id && item.revision < next.revision ? next : item,
        ),
      ),
    [],
  );
  const create = async (parentId: string | null) => {
    const owner = createOwner.current;
    if (!owner.active || owner.pending || owner.spaceId !== space.id) return;
    owner.pending = true;
    const controller = new AbortController();
    owner.controller = controller;
    setCreating({ spaceId: space.id, pending: true });
    try {
      const next = await api<Page>(
        `/spaces/${space.id}/pages`,
        'POST',
        {
          title: 'Başlıksız sayfa',
          content: '',
          parentId,
        },
        controller.signal,
      );
      if (
        !owner.active ||
        createOwner.current !== owner ||
        controller.signal.aborted
      )
        return;
      if (
        !next ||
        next.spaceId !== space.id ||
        typeof next.id !== 'string' ||
        !Number.isSafeInteger(next.revision) ||
        next.revision < 1
      )
        throw new Error('Oluşturulan sayfanın kimliği doğrulanamadı.');
      setPages((previous) => mergePageSnapshot(previous, [next]));
      onPage(next.id);
    } catch (e) {
      if (
        owner.active &&
        createOwner.current === owner &&
        !controller.signal.aborted
      )
        setError(errorText(e, 'Sayfa oluşturulamadı.'));
    } finally {
      owner.pending = false;
      if (owner.active && createOwner.current === owner)
        setCreating({ spaceId: space.id, pending: false });
    }
  };
  return (
    <main
      aria-label="Alan belgeleri"
      className={`spaces-surface ${pageId ? 'writing' : 'library'}`}
    >
      {error && (
        <div className="document-load-error" role="alert">
          {error}
        </div>
      )}
      {createPending && <p role="status">Sayfa oluşturuluyor…</p>}
      {!pageId ? (
        <SpaceLibrary
          space={space}
          pages={pages}
          onPage={onPage}
          onNew={() => void create(null)}
          pending={createPending}
        />
      ) : page ? (
        <div className="space-writing-layout">
          {outline && (
            <PageOutline
              pages={pages}
              selected={page.id}
              onPage={(id) => {
                onPage(id);
                if (window.innerWidth < 760) setOutline(false);
              }}
              onNew={() => void create(null)}
              pending={createPending}
              onClose={() => setOutline(false)}
            />
          )}
          <PageDocument
            key={page.id}
            page={page}
            pages={pages}
            workspace={workspace}
            paused={paused}
            onHome={() => onPage()}
            onOutline={() => setOutline(!outline)}
            onSubpage={() => void create(page.id)}
            onDirty={onDirty}
            onSaved={saved}
            onRefresh={onRefresh}
            onSchedule={onSchedule}
            onThread={onThread}
            onSettings={onSettings}
            onCreateDot={onCreateDot}
          />
        </div>
      ) : (
        <div className="library-empty">
          <h2>{loaded ? 'Sayfa bulunamadı' : 'Sayfa yükleniyor…'}</h2>
          {loaded && (
            <button className="document-primary" onClick={() => onPage()}>
              Tüm sayfalara dön
            </button>
          )}
        </div>
      )}
    </main>
  );
}
