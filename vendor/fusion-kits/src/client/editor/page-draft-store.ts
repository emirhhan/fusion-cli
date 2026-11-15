import type { PageDraft } from './autosave';
export type DraftScope = { ownerId: string; spaceId: string; pageId: string };
export type DraftSnapshot = {
  baseRevision: number;
  base: PageDraft;
  draft: PageDraft;
};
export type DraftRecord = { revision: number; snapshot: DraftSnapshot | null };
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem'>;
type Locks = {
  request<T>(name: string, callback: () => T | Promise<T>): Promise<T>;
};
const invalid = () =>
  new Error('Yerel taslak doğrulanamadı. Mevcut kayıt değiştirilmedi.');
function validDraft(value: unknown): value is PageDraft {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<PageDraft>;
  return (
    typeof item.title === 'string' &&
    item.title.length <= 160 &&
    typeof item.content === 'string' &&
    item.content.length <= 100000 &&
    (item.parentId === null ||
      (typeof item.parentId === 'string' && !!item.parentId))
  );
}
function validSnapshot(value: unknown): value is DraftSnapshot | null {
  if (value === null) return true;
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<DraftSnapshot>;
  return (
    Number.isSafeInteger(item.baseRevision) &&
    (item.baseRevision ?? 0) > 0 &&
    validDraft(item.base) &&
    validDraft(item.draft)
  );
}
export class PageDraftStore {
  constructor(
    private storage: Storage,
    private locks: Locks | undefined,
  ) {}
  private key(scope: DraftScope) {
    if (
      !Object.values(scope).every(
        (v) => typeof v === 'string' && v.length > 0 && v.length <= 500,
      )
    )
      throw invalid();
    return `fusion.page-draft.v1:${JSON.stringify([scope.ownerId, scope.spaceId, scope.pageId])}`;
  }
  private load(key: string, scope: DraftScope): DraftRecord {
    const raw = this.storage.getItem(key);
    if (raw === null) return { revision: 0, snapshot: null };
    let value;
    try {
      value = JSON.parse(raw);
    } catch {
      throw invalid();
    }
    if (
      !value ||
      value.schema !== 1 ||
      value.ownerId !== scope.ownerId ||
      value.spaceId !== scope.spaceId ||
      value.pageId !== scope.pageId ||
      !Number.isSafeInteger(value.revision) ||
      value.revision < 1 ||
      !validSnapshot(value.snapshot)
    )
      throw invalid();
    return { revision: value.revision, snapshot: value.snapshot };
  }
  async read(scope: DraftScope): Promise<DraftRecord> {
    const key = this.key(scope);
    if (!this.locks)
      throw new Error(
        'Bu ortamda güvenli yerel taslak saklama kullanılamıyor.',
      );
    return this.locks.request(key, () => this.load(key, scope));
  }
  async write(
    scope: DraftScope,
    expected: number,
    snapshot: DraftSnapshot | null,
  ): Promise<DraftRecord> {
    const key = this.key(scope);
    if (!this.locks)
      throw new Error(
        'Bu ortamda güvenli yerel taslak saklama kullanılamıyor.',
      );
    if (
      !Number.isSafeInteger(expected) ||
      expected < 0 ||
      !validSnapshot(snapshot)
    )
      throw invalid();
    return this.locks.request(key, () => {
      const current = this.load(key, scope);
      if (current.revision !== expected)
        throw new Error(
          'Yerel taslak başka bir sekmede değişti. Taslağını indirip iki sürümü karşılaştır.',
        );
      const revision = current.revision + 1;
      if (!Number.isSafeInteger(revision)) throw invalid();
      this.storage.setItem(
        key,
        JSON.stringify({ schema: 1, ...scope, revision, snapshot }),
      );
      return { revision, snapshot };
    });
  }
}
