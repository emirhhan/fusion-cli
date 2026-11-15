/**
 * Okunmamış sohbetler ve Dock rozeti (P-047).
 *
 * Okunmamış kümesi pencereye özgüdür ve kalıcılaştırılmaz: uygulama yeniden açılınca
 * kullanıcı zaten her şeyi "görmüş" sayılır. Rozet sayısı kümenin boyutudur; küme
 * boşalınca rozet kaldırılır. Tauri kabuğu yoksa (tarayıcı/test) rozet sessizce atlanır.
 */

export type RozetAyarlayici = (sayi: number) => Promise<void>;

const aboneler = new Set<() => void>();
let okunmamis: ReadonlySet<string> = new Set();

async function varsayilanRozet(sayi: number): Promise<void> {
  if (!("__TAURI_INTERNALS__" in window)) return;
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow().setBadgeCount(sayi > 0 ? sayi : undefined);
}

let rozetAyarla: RozetAyarlayici = varsayilanRozet;

function duyur(): void {
  for (const listener of aboneler) listener();
  // Rozet hatası (izin yok, platform desteklemiyor) arayüzü bozmaz; konsola düşer.
  void rozetAyarla(okunmamis.size).catch((error: unknown) => console.warn("Dock rozeti ayarlanamadı", error));
}

export function subscribeUnread(listener: () => void): () => void {
  aboneler.add(listener);
  return () => {
    aboneler.delete(listener);
  };
}

export function getUnread(): ReadonlySet<string> {
  return okunmamis;
}

export function markUnread(ids: Iterable<string>): void {
  const sonraki = new Set(okunmamis);
  let degisti = false;
  for (const id of ids) {
    if (!sonraki.has(id)) {
      sonraki.add(id);
      degisti = true;
    }
  }
  if (!degisti) return;
  okunmamis = sonraki;
  duyur();
}

export function clearUnread(id: string): void {
  if (!okunmamis.has(id)) return;
  const sonraki = new Set(okunmamis);
  sonraki.delete(id);
  okunmamis = sonraki;
  duyur();
}

/** Testler için: rozet yazıcısını değiştir ve kümeyi sıfırla. */
export function resetUnread(ayarlayici: RozetAyarlayici = varsayilanRozet): void {
  okunmamis = new Set();
  rozetAyarla = ayarlayici;
}
