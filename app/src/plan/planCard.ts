// Plan onay kartı (#325): seçenekler çekirdeğin `plan.kart` yanıtından okunur.

export type PlanSecenegi = { deger: string; etiket: string; aciklama: string };
export type PlanKarti = { secenekler: PlanSecenegi[]; onerilen: string };

/** `plan.kart` yanıtını doğrula; bekleyen plan yoksa ya da biçim bozuksa `null`. */
export function planKartiOku(raw: unknown): PlanKarti | null {
  if (!raw || typeof raw !== "object") return null;
  const veri = raw as Record<string, unknown>;
  if (veri.bekliyor !== true || !Array.isArray(veri.secenekler)) return null;
  const secenekler = veri.secenekler.flatMap((item): PlanSecenegi[] => {
    if (!item || typeof item !== "object") return [];
    const { deger, etiket, aciklama } = item as Record<string, unknown>;
    if (typeof deger !== "string" || typeof etiket !== "string") return [];
    return [{ deger, etiket, aciklama: typeof aciklama === "string" ? aciklama : "" }];
  });
  if (secenekler.length === 0) return null;
  const onerilen = typeof veri.onerilen === "string" ? veri.onerilen : secenekler[0].etiket;
  return { secenekler, onerilen };
}
