import type { Page } from '../../server/pages';
import type { DraftSnapshot } from './page-draft-store';
import type { PageConflictSnapshot } from './page-conflict';
export type PageDraft = Pick<Page, 'title' | 'content' | 'parentId'>;
export type SaveState = {
  page?: Page;
  draft?: PageDraft;
  remote?: Page;
  status: 'saved' | 'dirty' | 'saving' | 'error' | 'conflict';
  error?: string;
  storageError?: string;
  draftLoading?: boolean;
};
export type SavePage = (
  id: string,
  patch: PageDraft & { expectedRevision: number },
  signal: AbortSignal,
  scope: { spaceId: string },
) => Promise<Page>;
const fields = (page: Page): PageDraft => ({
  title: page.title,
  content: page.content,
  parentId: page.parentId,
});
const equal = (a: PageDraft, b: PageDraft) =>
  a.title === b.title && a.content === b.content && a.parentId === b.parentId;
export class PageAutosave {
  private state: SaveState = { status: 'saved' };
  private listeners = new Set<() => void>();
  private timer?: ReturnType<typeof setTimeout>;
  private controller?: AbortController;
  private pending?: Promise<boolean>;
  private generation = 0;
  private draftRead?: symbol;
  constructor(
    private save: SavePage,
    private onSaved?: (page: Page) => void,
  ) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private publish(patch: Partial<SaveState>) {
    this.state = { ...this.state, ...patch };
    for (const listener of this.listeners) listener();
  }
  private get changed() {
    return !!(
      this.state.page &&
      this.state.draft &&
      !equal(fields(this.state.page), this.state.draft)
    );
  }
  get dirty() {
    return (
      !!this.pending ||
      this.changed ||
      ['error', 'conflict'].includes(this.state.status)
    );
  }
  storageWarning(message?: string) {
    this.publish({ storageError: message });
  }
  beginDraftRead() {
    const token = Symbol();
    this.draftRead = token;
    this.publish({ draftLoading: true, storageError: undefined });
    return token;
  }
  endDraftRead(token: symbol) {
    if (this.draftRead !== token) return;
    this.draftRead = undefined;
    this.publish({ draftLoading: false });
  }
  restoreDraft(snapshot: DraftSnapshot) {
    const page = this.state.page;
    if (!page || this.changed || this.pending) return false;
    const conflict =
      page.revision !== snapshot.baseRevision ||
      !equal(fields(page), snapshot.base);
    this.publish({
      page: { ...page, ...snapshot.base, revision: snapshot.baseRevision },
      remote: page,
      draft: snapshot.draft,
      status: conflict ? 'conflict' : 'dirty',
      error: conflict
        ? 'Yerel taslak geri geldi; sunucuda farklı bir sürüm var. Taslağını indirip karşılaştır.'
        : undefined,
    });
    this.schedule();
    return true;
  }
  receive(page: Page) {
    if (
      this.state.page?.id !== page.id ||
      this.state.page?.spaceId !== page.spaceId
    ) {
      this.generation++;
      clearTimeout(this.timer);
      this.controller?.abort();
      this.pending = undefined;
      this.publish({
        page,
        draft: fields(page),
        remote: page,
        status: 'saved',
        error: undefined,
      });
      return;
    }
    if (page.revision <= (this.state.remote?.revision ?? 0)) return;
    if (this.pending) {
      this.publish({ remote: page });
      return;
    }
    if (this.changed || this.state.status === 'conflict') {
      clearTimeout(this.timer);
      this.publish({
        remote: page,
        status: 'conflict',
        error:
          'Bu sayfa başka bir yerde değişti. Taslağın güvende. Son sürümü yüklemeden önce kopyala.',
      });
    } else
      this.publish({
        page,
        remote: page,
        draft: fields(page),
        status: 'saved',
        error: undefined,
      });
  }
  edit(patch: Partial<PageDraft>) {
    if (this.state.draftLoading) return;
    if (!this.state.draft) return;
    this.publish({ draft: { ...this.state.draft, ...patch } });
    if (['error', 'conflict'].includes(this.state.status)) return;
    this.publish({
      status: this.pending ? 'saving' : this.changed ? 'dirty' : 'saved',
      error: undefined,
    });
    this.schedule();
  }
  private schedule() {
    clearTimeout(this.timer);
    if (
      this.changed &&
      !this.pending &&
      !['error', 'conflict'].includes(this.state.status)
    )
      this.timer = setTimeout(() => void this.flush(), 800);
  }
  async flush(retry = false): Promise<boolean> {
    clearTimeout(this.timer);
    if (this.pending) {
      await this.pending;
      return this.changed ? this.flush(retry) : this.state.status === 'saved';
    }
    if (!this.state.page || !this.state.draft) return false;
    if (
      this.state.status === 'conflict' ||
      (this.state.status === 'error' && !retry)
    )
      return false;
    if (!this.changed && this.state.status !== 'error') {
      this.publish({ status: 'saved', error: undefined });
      return true;
    }
    const page = this.state.page,
      draft = { ...this.state.draft },
      generation = this.generation;
    if (
      !draft.title.trim() ||
      draft.title.length > 160 ||
      draft.content.length > 100000
    ) {
      this.publish({
        status: 'error',
        error:
          'En fazla 160 karakterlik bir başlık ve 100.000 karakterlik bir belge kullan. Taslağın hâlâ burada.',
      });
      return false;
    }
    this.controller = new AbortController();
    const controller = this.controller;
    this.publish({ status: 'saving', error: undefined });
    const pending = (async () => {
      let deadline: ReturnType<typeof setTimeout> | undefined;
      try {
        const result = await Promise.race([
          this.save(
            page.id,
            { ...draft, expectedRevision: page.revision },
            controller.signal,
            { spaceId: page.spaceId },
          ),
          new Promise<never>((_, reject) => {
            deadline = setTimeout(() => {
              controller.abort();
              reject(
                new Error(
                  'Kaydetme zaman aşımına uğradı. Taslağın güvende; bağlanınca yeniden dene.',
                ),
              );
            }, 10000);
          }),
        ]);
        if (generation !== this.generation) return false;
        if (
          !result ||
          result.id !== page.id ||
          result.spaceId !== page.spaceId ||
          !Number.isSafeInteger(result.revision) ||
          result.revision <= page.revision ||
          typeof result.title !== 'string' ||
          typeof result.content !== 'string'
        ) {
          throw new Error(
            'Kaydedilen sayfanın kimliği veya sürümü doğrulanamadı. Taslak korundu.',
          );
        }
        if (!equal(fields(result), { ...draft, title: draft.title.trim() })) {
          throw new Error(
            'Kaydetme yanıtı gönderilen taslakla eşleşmiyor. Taslak korundu; son sürümü kontrol et.',
          );
        }
        const unchanged = equal(this.state.draft!, draft);
        const remote =
          this.state.remote && this.state.remote.revision > result.revision
            ? this.state.remote
            : result;
        this.publish({
          page: result,
          remote,
          draft: unchanged ? fields(result) : this.state.draft,
        });
        this.publish({
          status:
            remote.revision > result.revision
              ? 'conflict'
              : this.changed
                ? 'dirty'
                : 'saved',
          error:
            remote.revision > result.revision
              ? 'Daha yeni bir sürüm var. Taslağın korundu.'
              : undefined,
        });
        if (this.state.status !== 'conflict') {
          try {
            this.onSaved?.(result);
          } catch {
            this.publish({
              error:
                'Sayfa kaydedildi. Görünümü güncellemek için sayfayı yeniden aç.',
            });
          }
        }
        return this.state.status !== 'conflict';
      } catch (error) {
        if (generation !== this.generation) return false;
        const conflict =
          error &&
          typeof error === 'object' &&
          'status' in error &&
          error.status === 409;
        this.publish({
          status: conflict ? 'conflict' : 'error',
          error: conflict
            ? 'Bu sayfa başka bir yerde değişti. Taslağın güvende. Son sürümü yüklemeden önce kopyala.'
            : error instanceof Error
              ? error.message
              : 'Kaydedilemedi. Taslağın güvende.',
        });
        return false;
      } finally {
        clearTimeout(deadline);
        if (generation === this.generation) {
          this.pending = undefined;
          this.publish({});
          this.schedule();
        }
      }
    })();
    this.pending = pending;
    const success = await pending;
    if (success && generation === this.generation && this.changed)
      return this.flush(retry);
    return success;
  }
  observeRemote(
    candidate: Page,
    expectedDraft: PageDraft,
    scope: Pick<Page, 'id' | 'spaceId'>,
  ): boolean {
    const current = this.state.page;
    if (
      !current ||
      current.id !== scope.id ||
      current.spaceId !== scope.spaceId ||
      candidate.id !== scope.id ||
      candidate.spaceId !== scope.spaceId ||
      this.state.draft !== expectedDraft ||
      !Number.isSafeInteger(candidate.revision) ||
      candidate.revision < current.revision ||
      typeof candidate.title !== 'string' ||
      typeof candidate.content !== 'string'
    )
      return false;
    this.receive(candidate);
    return true;
  }
  conflictSnapshot(): PageConflictSnapshot | null {
    const { page, draft, remote, status } = this.state;
    if (
      status !== 'conflict' ||
      !page ||
      !draft ||
      !remote ||
      this.pending ||
      remote.revision <= page.revision
    )
      return null;
    return {
      pageId: page.id,
      spaceId: page.spaceId,
      baseRevision: page.revision,
      remoteRevision: remote.revision,
      base: fields(page),
      local: { ...draft },
      remote: fields(remote),
    };
  }
  resolveConflict(snapshot: PageConflictSnapshot, merged: PageDraft): boolean {
    const { page, draft, remote, status } = this.state;
    if (
      status !== 'conflict' ||
      this.pending ||
      !page ||
      !draft ||
      !remote ||
      page.id !== snapshot.pageId ||
      page.spaceId !== snapshot.spaceId ||
      page.revision !== snapshot.baseRevision ||
      remote.revision !== snapshot.remoteRevision ||
      !equal(fields(page), snapshot.base) ||
      !equal(fields(remote), snapshot.remote) ||
      !equal(draft, snapshot.local)
    )
      return false;
    this.generation++;
    clearTimeout(this.timer);
    this.publish({
      page: remote,
      draft: { ...merged },
      status: equal(fields(remote), merged) ? 'saved' : 'dirty',
      error: undefined,
    });
    this.schedule();
    return true;
  }
  useLatest() {
    const page = this.state.remote;
    if (!page) return;
    this.generation++;
    clearTimeout(this.timer);
    this.controller?.abort();
    this.pending = undefined;
    this.publish({
      page,
      draft: fields(page),
      remote: page,
      status: 'saved',
      error: undefined,
    });
  }
  dispose() {
    this.generation++;
    clearTimeout(this.timer);
    this.controller?.abort();
    this.pending = undefined;
    this.listeners.clear();
  }
}
