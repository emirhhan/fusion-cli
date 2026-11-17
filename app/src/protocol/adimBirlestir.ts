import type { OlayAdimi } from "./olayMetni";

export function ayniAracCagrisi(left: OlayAdimi, right: OlayAdimi): boolean {
  return !!left.callId && left.callId === right.callId && left.arac === right.arac &&
    left.sessionId === right.sessionId && left.turnId === right.turnId && left.attemptId === right.attemptId;
}

export function bitenAracAdimi(started: OlayAdimi, finished: OlayAdimi): OlayAdimi {
  return { ...finished, metin: started.metin, kaynak: started.kaynak ?? finished.kaynak, basladi: false };
}

function kimliksiz(adim: OlayAdimi): boolean {
  return !adim.callId && !adim.sessionId && !adim.turnId && !adim.attemptId && !adim.eventId;
}

/**
 * Biten aracı, başladığı adımın YERİNE yaz: Claude'daki gibi her araç tek satır
 * kalır ("src/app.py okunuyor" → bitince aynı satır, sonucuyla). Eskiden biten
 * araç "araç çalıştı: read_file" diye ayrı ve anlamsız bir satır açıyordu.
 */
export function adimiEkle(adimlar: OlayAdimi[], adim: OlayAdimi): OlayAdimi[] {
  const son = adimlar[adimlar.length - 1];
  if (adim.arac && !adim.basladi && son?.basladi && son.arac === adim.arac &&
      (ayniAracCagrisi(son, adim) || (kimliksiz(son) && kimliksiz(adim)))) {
    const birlesik = bitenAracAdimi(son, adim);
    return [...adimlar.slice(0, -1), birlesik];
  }
  return [...adimlar, adim];
}
