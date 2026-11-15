import { PageAutosave } from './autosave';
import {
  PageDraftStore,
  type DraftScope,
  type DraftSnapshot,
} from './page-draft-store';
const same = (a: unknown, b: unknown) =>
  JSON.stringify(a) === JSON.stringify(b);
/** One editor owns one CAS chain; cleanup drains admitted local writes only. */
export function bindPageDraft(
  controller: PageAutosave,
  store: PageDraftStore,
  scope: DraftScope,
) {
  let active = true;
  let revision = 0;
  let last: DraftSnapshot | null = null;
  let blocked = false;
  let unsubscribe = () => {};
  let chain: Promise<unknown>;
  const token = controller.beginDraftRead();
  let deadline: ReturnType<typeof setTimeout>;
  const snapshot = (): DraftSnapshot | null => {
    const state = controller.getSnapshot();
    const page = state.page,
      draft = state.draft;
    if (
      !page ||
      !draft ||
      page.id !== scope.pageId ||
      page.spaceId !== scope.spaceId
    )
      return null;
    const base = {
      title: page.title,
      content: page.content,
      parentId: page.parentId,
    };
    return same(base, draft)
      ? null
      : { baseRevision: page.revision, base, draft: { ...draft } };
  };
  const fail = (error: unknown) => {
    blocked = true;
    if (active)
      controller.storageWarning(
        `${error instanceof Error ? error.message : 'Yerel taslak saklanamadı.'} Uygulamayı kapatmadan önce taslağını indir.`,
      );
  };
  const capture = () => {
    if (!active || blocked) return;
    const page = controller.getSnapshot().page;
    if (page?.id !== scope.pageId || page.spaceId !== scope.spaceId) return;
    const next = snapshot();
    if (same(next, last)) return;
    last = next;
    chain = chain
      .then(async () => {
        if (blocked) return;
        const saved = await store.write(scope, revision, next);
        revision = saved.revision;
      })
      .catch(fail);
  };
  chain = Promise.race([
    store.read(scope),
    new Promise<never>((_, reject) => {
      deadline = setTimeout(
        () => reject(new Error('Yerel taslak okuması zaman aşımına uğradı.')),
        3000,
      );
    }),
  ])
    .then((record) => {
      if (!active) return;
      revision = record.revision;
      last = record.snapshot;
      if (last) {
        const state = controller.getSnapshot();
        const remote = state.page;
        const accepted =
          remote &&
          same(
            {
              title: remote.title,
              content: remote.content,
              parentId: remote.parentId,
            },
            last.draft,
          );
        if (!accepted && !controller.restoreDraft(last)) {
          throw new Error(
            'Kaydedilmiş yerel taslak ile yeni düzenleme çakıştı. Önce açık taslağını indir.',
          );
        }
      }
      unsubscribe = controller.subscribe(capture);
      capture();
    })
    .catch(fail)
    .finally(() => {
      clearTimeout(deadline);
      if (active) controller.endDraftRead(token);
    });
  return {
    dispose() {
      active = false;
      unsubscribe();
      controller.endDraftRead(token);
    },
    settled: async () => {
      let current;
      do {
        current = chain;
        await current;
      } while (current !== chain);
    },
  };
}
