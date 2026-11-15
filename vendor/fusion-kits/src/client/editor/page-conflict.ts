import type { PageDraft } from './autosave';

export interface PageConflictSnapshot {
  pageId: string;
  spaceId: string;
  baseRevision: number;
  remoteRevision: number;
  base: Readonly<PageDraft>;
  local: Readonly<PageDraft>;
  remote: Readonly<PageDraft>;
}

/** Çakışan alanlarda karar verme; yalnız tek taraflı değişiklikleri öner. */
export function suggestPageMerge(snapshot: PageConflictSnapshot): {
  draft: PageDraft;
  conflicts: Array<keyof PageDraft>;
} {
  const draft = { ...snapshot.local };
  const conflicts: Array<keyof PageDraft> = [];
  for (const field of ['title', 'content', 'parentId'] as const) {
    const base = snapshot.base[field];
    const local = snapshot.local[field];
    const remote = snapshot.remote[field];
    if (local === base) {
      if (field === 'parentId') draft.parentId = snapshot.remote.parentId;
      else if (field === 'title') draft.title = snapshot.remote.title;
      else draft.content = snapshot.remote.content;
    } else if (remote !== base && local !== remote) conflicts.push(field);
  }
  return { draft, conflicts };
}
