import type { BildirimTercihleri } from "./preferences";

/**
 * Tur/onay geçişlerinden bildirim PLANI çıkaran saf mantık (P-047).
 *
 * Kural Claude Code masaüstündeki gibidir: kullanıcı o sohbete BAKMIYORSA haber
 * verilir. "Bakmak" = sohbet seçili VE pencere odakta. Bakılan sohbette onay kartı
 * zaten görünür, tur bitişi zaten ekranda; bildirim gürültü olur.
 *
 * Bu modül ne Tauri ne React bilir: giriş iki anlık görüntü, çıkış yapılacaklar
 * listesi. Kanca (`useTurnNotifications`) planı işletir.
 */

export interface OturumIzi {
  running: boolean;
  /** Bekleyen onay/soru kimliği; yoksa null. */
  questionId: string | null;
  title: string;
}

export type BildirimTuru = "tur-bitti" | "onay-bekliyor" | "arka-plan-bitti";

export interface PlanlananBildirim {
  tur: BildirimTuru;
  oturumId: string;
  baslik: string;
  metin: string;
  /** Bakılmayan sohbet: kenar çubuğunda okunmamış işareti de konur. */
  okunmamis: boolean;
  /** Pencere odaktayken de gönderilsin (arka plandaki sohbet). */
  odaktaDaGonder: boolean;
}

export interface BakisDurumu {
  activeId: string | null;
  focused: boolean;
}

export const BILDIRIM_METINLERI: Record<BildirimTuru, { baslik: string; metin: (title: string) => string }> = {
  "tur-bitti": { baslik: "Fusion işini bitirdi", metin: (title) => `"${title}" sohbetinde cevap hazır.` },
  "onay-bekliyor": { baslik: "Fusion onayını bekliyor", metin: (title) => `"${title}" sohbeti bir onay ya da cevap bekliyor.` },
  "arka-plan-bitti": { baslik: "Arka plandaki sohbet bitti", metin: (title) => `"${title}" sohbetinde cevap hazır.` },
};

function bildirim(tur: BildirimTuru, oturumId: string, title: string, odaktaDaGonder: boolean): PlanlananBildirim {
  const metin = BILDIRIM_METINLERI[tur];
  return { tur, oturumId, baslik: metin.baslik, metin: metin.metin(title), okunmamis: true, odaktaDaGonder };
}

/**
 * İki anlık görüntü arasındaki geçişlerden bildirimleri çıkar.
 *
 * - `running` true → false: bakılan sohbetse yalnız odak yokken "tur bitti";
 *   bakılmayan sohbetse odak olsa da "arka plan bitti" (kullanıcı başka sohbettedir).
 * - soru null → dolu: bakılan ve odaktaysa kart zaten görünür, bildirilmez; değilse
 *   "onay bekliyor".
 * - İlk kez görülen (geri yüklenen) sohbet geçiş sayılmaz: açılışta bildirim yağmaz.
 */
export function planNotifications(
  previous: Record<string, OturumIzi>,
  current: Record<string, OturumIzi>,
  bakis: BakisDurumu,
  tercihler: BildirimTercihleri,
): PlanlananBildirim[] {
  const plan: PlanlananBildirim[] = [];
  for (const [id, simdi] of Object.entries(current)) {
    const once = previous[id];
    if (!once) continue;
    const bakiliyor = bakis.activeId === id && bakis.focused;
    if (once.running && !simdi.running) {
      if (bakis.activeId === id) {
        if (!bakis.focused && tercihler.turBitti) plan.push(bildirim("tur-bitti", id, simdi.title, false));
      } else if (tercihler.arkaPlanBitti) {
        plan.push(bildirim("arka-plan-bitti", id, simdi.title, true));
      }
    }
    if (!once.questionId && simdi.questionId && !bakiliyor && tercihler.onayBekliyor) {
      plan.push(bildirim("onay-bekliyor", id, simdi.title, bakis.activeId !== id));
    }
  }
  return plan;
}

/** Bildirim üretilmese de okunmamış sayılacak geçişler (tercih kapalı olsa bile). */
export function unreadTransitions(
  previous: Record<string, OturumIzi>,
  current: Record<string, OturumIzi>,
  bakis: BakisDurumu,
): string[] {
  const ids: string[] = [];
  for (const [id, simdi] of Object.entries(current)) {
    const once = previous[id];
    if (!once) continue;
    const bakiliyor = bakis.activeId === id && bakis.focused;
    if (bakiliyor) continue;
    const bitti = once.running && !simdi.running;
    const soruGeldi = !once.questionId && Boolean(simdi.questionId);
    if (bitti || soruGeldi) ids.push(id);
  }
  return ids;
}
