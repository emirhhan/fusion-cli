/** Yalnız kimlik saklanır; istem, hesap veya referans içeriği saklanmaz. */
const JOURNAL_VERSION = 1;
const MAX_PENDING_JOBS = 256;
const VALID_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/;
const QUARANTINE_PREFIX = "fusion:image-jobs-quarantine:";

function parseRecord(raw: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(raw);
    return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
  } catch { return null; }
}

export class ImageJobJournal {
  private readonly prefix: string;
  constructor(private readonly storage: Storage, scope: string) {
    if (!scope || scope.length > 8192) throw new Error("Görsel işinin sohbet kapsamı geçersiz.");
    this.prefix = `fusion:image-jobs:${encodeURIComponent(scope)}:`;
  }

  /**
   * Bekleyen iş kimlikleri. Gelecek sürümün kaydı (canlı, ücretli bir iş olabilir)
   * okunamazsa yeni üretim durur. Okunamayan BOZUK kayıt ise karantinaya taşınır ve
   * sağlam işler açılır. Ölçüldü (29 Ekim): tek bozuk kayıt sohbetteki bütün bekleyen
   * işleri ve yeni üretimi kalıcı olarak kilitliyordu; kimliği okunamayan kaydı
   * beklemek hiçbir işi uzlaştırmaz.
   */
  read(): string[] {
    try {
      const ids: string[] = [];
      const corrupt: string[] = [];
      for (let index = 0; index < this.storage.length; index++) {
        const key = this.storage.key(index);
        if (!key?.startsWith(this.prefix)) continue;
        const raw = this.storage.getItem(key);
        if (raw === null) continue;
        const record = parseRecord(raw);
        if (record === null) { corrupt.push(key); continue; }
        if (record.version !== JOURNAL_VERSION) throw new Error();
        if (typeof record.jobId !== "string" || !VALID_ID.test(record.jobId)
          || key !== this.key(record.jobId) || Object.keys(record).length !== 2) { corrupt.push(key); continue; }
        ids.push(record.jobId);
        if (ids.length > MAX_PENDING_JOBS) throw new Error();
      }
      for (const key of corrupt) this.quarantine(key);
      return ids.sort();
    } catch { throw new Error("Bekleyen görsel işlerinin kaydı doğrulanamadı; yeni üretim başlatılmadı."); }
  }

  /** Ham kayıt teşhis için saklanır; iş listesinden çıkar. Taşınamazsa okuma durur. */
  private quarantine(key: string): void {
    const raw = this.storage.getItem(key);
    if (raw === null) return;
    const target = QUARANTINE_PREFIX + key.slice("fusion:image-jobs:".length);
    this.storage.setItem(target, raw);
    if (this.storage.getItem(target) !== raw) throw new Error();
    this.storage.removeItem(key);
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
