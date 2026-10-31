/**
 * Bildirim tercihleri — hangi olay işletim sistemi bildirimi üretir, ses çalar mı.
 *
 * `settings/preferences.ts` ile aynı kalıp: depo enjekte edilebilir, erişim düşerse
 * varsayılanlar kullanılır, `useSyncExternalStore` ile açık ekranlar aynı değeri okur.
 * Varsayılanlar GÜVENLİ tarafta: bildirimler açık (Claude Code masaüstü de tur bitince
 * ve izin beklerken bildirir), ses kapalı (sesli uyarı istenmeden çalmaz).
 */

export const NOTIFICATION_STORAGE_KEY = "fusion.notifications.v1";

export interface BildirimTercihleri {
  /** Bakılan sohbetin turu bitince (pencere odakta değilken) bildir. */
  turBitti: boolean;
  /** Onay ya da soru beklerken bildir. */
  onayBekliyor: boolean;
  /** Bakılmayan (arka plandaki ya da zamanlanmış) sohbetin turu bitince bildir. */
  arkaPlanBitti: boolean;
  /** Bildirimle birlikte kısa bir ses çal. */
  ses: boolean;
}

export const VARSAYILAN_BILDIRIM_TERCIHLERI: BildirimTercihleri = {
  turBitti: true,
  onayBekliyor: true,
  arkaPlanBitti: true,
  ses: false,
};

const ANAHTARLAR = Object.keys(VARSAYILAN_BILDIRIM_TERCIHLERI) as (keyof BildirimTercihleri)[];

/** Saklı değeri varsayılanlarla birleştir; bilinmeyen/bozuk alanlar varsayılana düşer. */
export function parseNotificationPreferences(raw: string | null): BildirimTercihleri {
  if (!raw) return VARSAYILAN_BILDIRIM_TERCIHLERI;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return VARSAYILAN_BILDIRIM_TERCIHLERI;
    const kayit = parsed as Record<string, unknown>;
    const sonuc = { ...VARSAYILAN_BILDIRIM_TERCIHLERI };
    for (const anahtar of ANAHTARLAR) {
      if (typeof kayit[anahtar] === "boolean") sonuc[anahtar] = kayit[anahtar] as boolean;
    }
    return sonuc;
  } catch {
    return VARSAYILAN_BILDIRIM_TERCIHLERI;
  }
}

export function readNotificationPreferences(storage?: Pick<Storage, "getItem">): BildirimTercihleri {
  try {
    return parseNotificationPreferences((storage ?? localStorage).getItem(NOTIFICATION_STORAGE_KEY));
  } catch {
    return VARSAYILAN_BILDIRIM_TERCIHLERI;
  }
}

export function saveNotificationPreferences(
  tercihler: BildirimTercihleri,
  storage?: Pick<Storage, "setItem">,
): void {
  try {
    (storage ?? localStorage).setItem(NOTIFICATION_STORAGE_KEY, JSON.stringify(tercihler));
  } catch {
    // Tercih kalıcılaşmasa da bu pencerede uygulanır.
  }
}

const aboneler = new Set<() => void>();
let anlik: BildirimTercihleri | null = null;

function anlikDeger(): BildirimTercihleri {
  if (anlik === null) anlik = readNotificationPreferences();
  return anlik;
}

export function subscribeNotificationPreferences(listener: () => void): () => void {
  aboneler.add(listener);
  return () => {
    aboneler.delete(listener);
  };
}

export function getNotificationPreferences(): BildirimTercihleri {
  return anlikDeger();
}

/** Tek alanı değiştir: hem kalıcılaştır hem açık ekranlara duyur. */
export function setNotificationPreference<K extends keyof BildirimTercihleri>(
  anahtar: K,
  deger: BildirimTercihleri[K],
): void {
  anlik = { ...anlikDeger(), [anahtar]: deger };
  saveNotificationPreferences(anlik);
  for (const listener of aboneler) listener();
}

/** Testlerin depoyu sıfırlaması için; üretimde çağrılmaz. */
export function resetNotificationPreferencesCache(): void {
  anlik = null;
}
