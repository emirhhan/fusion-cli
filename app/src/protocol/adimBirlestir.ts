import type { OlayAdimi } from "./olayMetni";

export function ayniAracCagrisi(left: OlayAdimi, right: OlayAdimi): boolean {
  if (!left.callId || left.callId !== right.callId ||
      left.sessionId !== right.sessionId || left.turnId !== right.turnId || left.attemptId !== right.attemptId) {
    return false;
  }
  // Tam tel kimliği aynı çağrıyı taşır; yürütücü araç adını yeniden yazabilir.
  // Eksik/eski kimlikte yalnız aynı ad eşleşir.
  const tamKimlik = [left.callId, left.sessionId, left.turnId, left.attemptId].every(value => !!value?.trim());
  return left.arac === right.arac || (!!left.arac && !!right.arac && tamKimlik);
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
  if (adim.arac && !adim.basladi && son?.basladi &&
      (ayniAracCagrisi(son, adim) || (son.arac === adim.arac && kimliksiz(son) && kimliksiz(adim)))) {
    const birlesik = bitenAracAdimi(son, adim);
    return [...adimlar.slice(0, -1), birlesik];
  }
  return [...adimlar, adim];
}
