/**
 * Görünüm tercihleri — tarayıcı deposunda, hesaptan bağımsız.
 *
 * `theme.ts` ile aynı kalıp: okuma/yazma ayrı fonksiyonlar, depo enjekte
 * edilebilir ve erişim düşerse uygulama ÇALIŞMAYA DEVAM EDER. Özel pencerede
 * `localStorage` erişimi istisna fırlatabiliyor; bir tercih okunamadı diye
 * sohbetin açılmaması kabul edilemez.
 */

export const STEPS_STORAGE_KEY = "fusion.conversation.show-steps";

/**
 * Adım dökümü görünsün mü?
 *
 * Varsayılan KAPALI. Ölçülmüş şikayet: her cevabın üstünde "düşünüyor",
 * "araç çalıştı" gibi satırlar birikiyor ve basit bir soruda bile kullanıcı
 * cevabı bulmak için kaydırıyordu. İlgilenen açar.
 */
export function readShowSteps(storage: Pick<Storage, "getItem"> = localStorage): boolean {
  try {
    return storage.getItem(STEPS_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function saveShowSteps(
  visible: boolean,
  storage: Pick<Storage, "setItem"> = localStorage,
): void {
  try {
    storage.setItem(STEPS_STORAGE_KEY, String(visible));
  } catch {
    // Tercih kalıcılaştırılamasa da bu pencerede uygulanır.
  }
}

/**
 * Tercihi paylaşan küçük depo.
 *
 * Ayarlardaki anahtar ile sohbetteki gösterim AYNI değeri okumalı: iki ayrı
 * `useState` olsaydı anahtarı değiştirmek açık sohbeti etkilemez, kullanıcı
 * ayarın işlemediğini sanırdı. `useSyncExternalStore` eşzamanlı çizimde de
 * doğru olan yoldur.
 */
const aboneler = new Set<() => void>();
let gosterilsin: boolean | null = null;

function anlikDeger(): boolean {
  if (gosterilsin === null) gosterilsin = readShowSteps();
  return gosterilsin;
}

export function subscribeShowSteps(listener: () => void): () => void {
  aboneler.add(listener);
  return () => {
    aboneler.delete(listener);
  };
}

export function getShowSteps(): boolean {
  return anlikDeger();
}

/** Tercihi değiştir: hem kalıcılaştır hem açık ekranlara duyur. */
export function setShowSteps(visible: boolean): void {
  gosterilsin = visible;
  saveShowSteps(visible);
  for (const listener of aboneler) listener();
}

/** Testlerin depoyu sıfırlaması için; üretimde çağrılmaz. */
export function resetShowStepsCache(): void {
  gosterilsin = null;
}
