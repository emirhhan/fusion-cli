/**
 * Sohbet başlığı kuralları (arayüz tarafı).
 *
 * Başlığın KENDİSİ çekirdekte üretilir (`sohbet.baslik`, bkz.
 * `appserver/conversation_title.py`): saklı sohbet listesi de aynı sezgiselle
 * adlandırılır ve iki ayrı kural ayrışmasın diye tek yerde durur. Burada yalnız
 * "başlık ne zaman değiştirilebilir" kuralı vardır.
 */

/** Henüz mesaj yazılmamış sekmenin adı. */
export const DEFAULT_TITLE = "Yeni görev";

/**
 * Önerilen başlık uygulanabilir mi?
 *
 * Yalnız varsayılan adı taşıyan sekme adlandırılır: kullanıcının verdiği,
 * devralınan (`[claude] …`) ya da geri açılan sohbetin başlığı EZİLMEZ.
 * Boş öneri (mesajda anlamlı bir şey yok) sekmeyi varsayılan adında bırakır.
 */
export function canApplySuggestedTitle(current: string, suggested: string): boolean {
  return current === DEFAULT_TITLE && suggested.trim().length > 0;
}
