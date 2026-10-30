const STORAGE_KEY = "fusion.schedule-owner";

let cached: string | null = null;

function randomId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `pencere-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Vade yoklamasının sahiplik kimliği (`zamanlama.sahiplik`). Pencere başına tektir:
 * `sessionStorage` yeniden yüklemede korunur (kiranın süre dolmasını beklemeden devam),
 * yeni uygulama örneği/penceresi ise yeni kimlik alır ve kira başkasındayken yoklamaz.
 * Depolama kullanılamazsa bellekteki kimlik yeterlidir.
 */
export function schedulerOwnerId(options: { storage?: Storage; fresh?: boolean } = {}): string {
  if (cached && !options.fresh) return cached;
  let id: string | null = null;
  try {
    const storage = options.storage ?? sessionStorage;
    if (!options.fresh) id = storage.getItem(STORAGE_KEY);
    if (!id) {
      id = randomId();
      storage.setItem(STORAGE_KEY, id);
    }
  } catch {
    id ??= randomId();
  }
  cached = id;
  return id;
}
