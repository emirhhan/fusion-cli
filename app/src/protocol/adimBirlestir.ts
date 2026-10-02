import type { OlayAdimi } from "./olayMetni";

/**
 * Biten aracı, başladığı adımın YERİNE yaz: Claude'daki gibi her araç tek satır
 * kalır ("src/app.py okunuyor" → bitince aynı satır, sonucuyla). Eskiden biten
 * araç "araç çalıştı: read_file" diye ayrı ve anlamsız bir satır açıyordu.
 */
export function adimiEkle(adimlar: OlayAdimi[], adim: OlayAdimi): OlayAdimi[] {
  const son = adimlar[adimlar.length - 1];
  if (adim.arac && !adim.basladi && son?.basladi && son.arac === adim.arac) {
    const birlesik: OlayAdimi = { ...adim, metin: son.metin, kaynak: son.kaynak ?? adim.kaynak, basladi: false };
    return [...adimlar.slice(0, -1), birlesik];
  }
  return [...adimlar, adim];
}

