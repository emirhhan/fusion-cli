import type { Mesaj } from "../screens/Conversation";

/**
 * 53 bitlik hızlı özet (cyrb53). Kimlik içeriğin KENDİSİNİ değil özetini taşır: büyük yanıtta
 * `encodeURIComponent(içerik)` bellekte 2-3 katına çıkıyor, `startsWith`/`===` pahalıydı (U4-38).
 * Aynı içerik çakışmaları zaten `occurrence` sayacıyla ayrılır.
 */
function ozet(metin: string): string {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < metin.length; i += 1) {
    const kod = metin.charCodeAt(i);
    h1 = Math.imul(h1 ^ kod, 2654435761);
    h2 = Math.imul(h2 ^ kod, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
}

/** Eski döküm kimliği içerik ve aynı içeriğin occurrence'ına bağlanır. */
export function migrateMessageIds(messages: Mesaj[], namespace: string): Mesaj[] {
  const occurrences = new Map<string, number>();
  return messages.map((message) => {
    const content = JSON.stringify([message.rol, message.metin, message.ekler ?? []]);
    const occurrence = occurrences.get(content) ?? 0;
    occurrences.set(content, occurrence + 1);
    if (message.id) return message;
    return { ...message, id: `legacy:${namespace}:${ozet(content)}:${occurrence}` };
  });
}
