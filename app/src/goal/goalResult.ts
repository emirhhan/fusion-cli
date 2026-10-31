/**
 * `/goal` (P-058) tur sonucu: çekirdek her turdan sonra hedefi değerlendirir ve sonuca
 * `hedef` (karar metni) ile, koşul henüz karşılanmadıysa `hedef_devam` (sıradaki görev)
 * ekler. Arayüz karar metnini sohbete ara not olarak yazar ve devam görevini kullanıcı
 * mesajı olarak göstermeden normal gönderim yolundan sürer; Durdur zinciri keser.
 */
/** Sırada kullanıcı mesajı varken devam turu üretilmez (çekirdek `GOAL_WAITING_USER` ile aynı). */
export const GOAL_WAITING_USER = "Sırada mesajın var; hedef onu bekliyor (turdan sonra yeniden değerlendirilir).";

export interface GoalResult {
  /** Kullanıcıya gösterilecek karar metni ("◎ Hedef henüz karşılanmadı — …"). */
  metin: string;
  /** "devam" | "tamam" | "imkansiz" | "duraklatildi" | "durduruldu". */
  eylem: string;
  /** Doluysa hedef kipinde gönderilecek devam görevi. */
  devam: string | null;
}

export function decodeGoalResult(result: Record<string, unknown>): GoalResult | null {
  const hedef = result.hedef;
  if (!hedef || typeof hedef !== "object") return null;
  const kayit = hedef as Record<string, unknown>;
  const metin = typeof kayit.metin === "string" ? kayit.metin : "";
  if (!metin) return null;
  const devam = typeof result.hedef_devam === "string" && result.hedef_devam.trim() ? result.hedef_devam : null;
  return { metin, eylem: typeof kayit.eylem === "string" ? kayit.eylem : "", devam };
}
