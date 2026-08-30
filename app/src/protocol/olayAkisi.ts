import type { Mesaj } from "../screens/Conversation";
import { olayAdimi } from "./olayMetni";

/**
 * Olayı sohbet akışına ekle.
 *
 * Ardışık adımlar TEK bir çalışma bloğunda toplanır. Eskiden her olay ayrı bir
 * satır açıyordu ve iki model çağrısı üst üste iki özdeş "model düşünüyor…"
 * satırı olarak görünüyordu — kullanıcı bunu tekrar sandı, haklıydı.
 *
 * Turun sonucu ("görev tamamlandı") bloğa KATILMAZ: o bir adım değil, akışın
 * kapanışıdır ve kendi satırında durur.
 */
export function olayEkle(messages: Mesaj[], event: Record<string, unknown>): Mesaj[] {
  const adim = olayAdimi(event);
  if (!adim) return messages;

  if (adim.sonuc) {
    return [...messages, { rol: "olay", metin: adim.metin, adimlar: [adim] }];
  }

  const son = messages[messages.length - 1];
  const bloklanabilir = son?.rol === "olay" && !son.adimlar?.some((item) => item.sonuc);
  if (!bloklanabilir) {
    return [...messages, { rol: "olay", metin: adim.metin, adimlar: [adim] }];
  }

  const adimlar = [...(son.adimlar ?? []), adim];
  return [
    ...messages.slice(0, -1),
    { ...son, adimlar, metin: adim.metin },
  ];
}
