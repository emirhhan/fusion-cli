/**
 * Arayüz tercihlerinin çekirdekte yedeği.
 *
 * Webview `localStorage`'ı bazı kurulumlarda hiç yazılmıyor (bkz.
 * `tests/test_theme_persistence.py`); pencere düzeni, kenar çubuğu ve proje
 * kayıtları her açılışta sıfırlanıyordu. Aşağıdaki izinli anahtarlar yazıldığı
 * anda çekirdeğe de gönderilir ve açılışta çekirdekten geri yüklenir.
 * Sohbet taslakları ve ekli dosya içerikleri izinli listede DEĞİLDİR.
 */
import type { ProtocolClient } from "../protocol/client";

const MIRRORED_KEYS = new Set([
  "fusion.conversation.show-steps",
  "fusion.inspector.layout.v1",
  "fusion.inspector.placement",
  "fusion.last-project-root",
  "fusion.layout",
  "fusion.onboarding.completed.v1",
  "fusion.permission-explanations.v1",
  "fusion.projects.v1",
  "fusion.theme",
]);
const MIRRORED_PREFIXES = ["fusion.sidebar.", "fusion.session-mode."];

export function isMirroredKey(key: string): boolean {
  return MIRRORED_KEYS.has(key) || MIRRORED_PREFIXES.some((prefix) => key.startsWith(prefix));
}

type Target = Pick<Client, "request">;
type Client = Pick<ProtocolClient, "request">;
interface StorageLike {
  length: number;
  key(index: number): string | null;
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function localKeys(storage: StorageLike): string[] {
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key && isMirroredKey(key)) keys.push(key);
  }
  return keys;
}

/**
 * Çekirdekteki değerleri yerel depoya yazar (çekirdek kazanır), çekirdekte
 * olmayan yerel değerleri çekirdeğe taşır. Yerel depo değiştiyse `true` döner;
 * çağıran, açık ekranların yeni değerleri okuması için bir kez yeniler.
 */
export async function hydratePrefs(client: Target, storage: StorageLike = localStorage): Promise<boolean> {
  const result = await client.request("ayar.arayuz", {});
  if (result.ok !== true || typeof result.degerler !== "object" || result.degerler === null) {
    throw new Error(String(result.metin ?? "Arayüz tercihleri okunamadı."));
  }
  const remote = result.degerler as Record<string, unknown>;
  let changed = false;
  for (const [key, value] of Object.entries(remote)) {
    if (!isMirroredKey(key) || typeof value !== "string") continue;
    // Tek anahtarın yazılamaması (kota/SecurityError) kalanları atlatmaz ve
    // açılışı bozmaz; yazılamayan anahtar için yenileme de istenmez.
    try {
      if (storage.getItem(key) === value) continue;
      storage.setItem(key, value);
      changed = true;
    } catch { /* Depo yazılamıyorsa çekirdek değeri bu açılışta uygulanamaz. */ }
  }
  for (const key of localKeys(storage)) {
    const value = storage.getItem(key);
    // Reddedilen istek yakalanmazsa çökme diyaloğunu tetiklerdi.
    if (!(key in remote) && value !== null) void client.request("ayar.arayuz_kaydet", { anahtar: key, deger: value }).catch(() => undefined);
  }
  return changed;
}

/**
 * İzinli anahtar yazıldığında/silindiğinde çekirdeğe de bildirir. Dönen işlev
 * yamayı geri alır. Hata sessiz geçilmez: `onError`'a iletilir.
 *
 * Ölçüldü (29 Ekim): eski yama `finally` içinde gönderiyordu — yerel yazma
 * kota/SecurityError ile başarısız olsa da değer çekirdeğe gidiyordu; ayrıca
 * `sessionStorage` yazımlarını da yakalıyor, `clear()` ise hiç yamalı değildi.
 * Artık yalnız BAŞARILI yerel yazma yansıtılır, yalnız `kaynak` (varsayılan
 * `localStorage`) örneği izlenir ve `clear()` izinli anahtarları siler.
 */
export function installPrefsMirror(
  client: Target,
  onError: (message: string) => void = (message) => console.error(message),
  proto: Pick<Storage, "setItem" | "removeItem" | "clear"> = Storage.prototype,
  kaynak: object | undefined = proto === Storage.prototype ? varsayilanDepo() : undefined,
): () => void {
  const originalSet = proto.setItem;
  const originalRemove = proto.removeItem;
  const originalClear = proto.clear;
  const send = (key: string, value: string | null) => {
    if (!isMirroredKey(key)) return;
    void client.request("ayar.arayuz_kaydet", { anahtar: key, deger: value })
      .then((result) => { if (result.ok !== true) onError(String(result.metin ?? "Tercih kaydedilemedi.")); })
      .catch((reason: unknown) => onError(`Tercih kaydedilemedi: ${String(reason)}`));
  };
  const izlenen = (depo: unknown) => kaynak === undefined || depo === kaynak;
  proto.setItem = function patchedSet(this: Storage, key: string, value: string) {
    originalSet.call(this, key, value);
    if (izlenen(this)) send(key, String(value));
  };
  proto.removeItem = function patchedRemove(this: Storage, key: string) {
    originalRemove.call(this, key);
    if (izlenen(this)) send(key, null);
  };
  proto.clear = function patchedClear(this: Storage) {
    const anahtarlar = izlenen(this) ? localKeys(this) : [];
    originalClear.call(this);
    anahtarlar.forEach((key) => send(key, null));
  };
  return () => { proto.setItem = originalSet; proto.removeItem = originalRemove; proto.clear = originalClear; };
}

function varsayilanDepo(): object | undefined {
  try { return localStorage; } catch { return undefined; }
}
