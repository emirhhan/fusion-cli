/** Yalnız kimlik saklanır; istem, hesap veya referans içeriği saklanmaz. */
const JOURNAL_VERSION = 1;
const MAX_PENDING_JOBS = 256;
const VALID_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;

export class ImageJobJournal {
  private readonly prefix: string;
  constructor(private readonly storage: Storage, scope: string) {
    if (!scope || scope.length > 8192) throw new Error("Görsel işinin sohbet kapsamı geçersiz.");
    this.prefix = `fusion:image-jobs:${encodeURIComponent(scope)}:`;
  }

  read(): string[] {
    try {
      const ids: string[] = [];
      for (let index = 0; index < this.storage.length; index++) {
        const key = this.storage.key(index);
        if (!key?.startsWith(this.prefix)) continue;
        const raw = this.storage.getItem(key);
        if (raw === null) continue;
        const value: unknown = JSON.parse(raw);
        if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error();
        const record = value as Record<string, unknown>;
        if (record.version !== JOURNAL_VERSION || typeof record.jobId !== "string"
          || !VALID_ID.test(record.jobId) || key !== this.key(record.jobId)
          || Object.keys(record).length !== 2) throw new Error();
        ids.push(record.jobId);
        if (ids.length > MAX_PENDING_JOBS) throw new Error();
      }
      return ids.sort();
    } catch { throw new Error("Bekleyen görsel işlerinin kaydı doğrulanamadı; yeni üretim başlatılmadı."); }
  }

  add(jobId: string): void {
    const key = this.key(jobId);
    const current = this.read();
    if (!current.includes(jobId) && current.length >= MAX_PENDING_JOBS) throw new Error("Bekleyen görsel işlerinin sınırına ulaşıldı.");
    try {
      const value = JSON.stringify({ version: JOURNAL_VERSION, jobId });
      this.storage.setItem(key, value);
      if (this.storage.getItem(key) !== value) throw new Error();
    } catch { throw new Error("Görsel iş kimliği kaydedilemedi; üretim başlatılmadı."); }
  }

  remove(jobId: string): void {
    try {
      const key = this.key(jobId);
      this.storage.removeItem(key);
      if (this.storage.getItem(key) !== null) throw new Error();
    } catch { throw new Error("Görsel işinin yerel kaydı temizlenemedi; durumunu tekrar kontrol et."); }
  }

  private key(jobId: string): string {
    if (!VALID_ID.test(jobId)) throw new Error("Görsel iş kimliği geçersiz.");
    return this.prefix + jobId;
  }
}
