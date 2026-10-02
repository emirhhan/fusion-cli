import type { Mesaj } from "../screens/Conversation";
import { adimiEkle } from "../protocol/adimBirlestir";
import { olayAdimi, type OlayAdimi } from "../protocol/olayMetni";

/**
 * Alt ajan ekibinin olaylarını sohbet akışına kart olarak işle.
 *
 * Eskiden alt ajanın adımları ana turun adım listesine "alt ajan" rozetiyle
 * karışıyordu; iki ajan aynı anda koşunca satırlar iç içe geçiyordu. Çekirdek
 * artık her olaya `agent_id` basıyor: o kimliği taşıyan olay ana bloğa DEĞİL,
 * ajanın kendi kartına düşer. Aynı anda başlatılan ajanlar (`group_size`) tek
 * bir ekip mesajında yan yana durur — Codex'teki gibi.
 */

export type AjanDurumu = "calisiyor" | "bitti" | "yarim";

export interface AjanKarti {
  id: string;
  persona: string;
  unvan: string;
  avatar: string;
  renk: string;
  gorev: string;
  durum: AjanDurumu;
  adimlar: OlayAdimi[];
  /** Kartın başladığı sabit `Date.now()` (sayaç yeniden bağlanınca sıfırlanmasın). */
  baslangic: number;
  ozet?: string;
  sureSn?: number;
  cagriSayisi?: number;
}

function metin(deger: unknown): string {
  return typeof deger === "string" ? deger : "";
}

/** Olay bir ekip olayıysa güncel akışı, değilse `null` döndür. */
export function ekipOlayi(messages: Mesaj[], event: Record<string, unknown>): Mesaj[] | null {
  if (event.olay === "SubAgentStarted") return ajanBasladi(messages, event);
  if (event.olay === "SubAgentFinished") return ajanBitti(messages, event);
  const kimlik = metin(event.agent_id);
  if (!kimlik) return null;
  return ajanAdimi(messages, kimlik, event);
}

function ajanBasladi(messages: Mesaj[], event: Record<string, unknown>): Mesaj[] {
  const kart: AjanKarti = {
    id: metin(event.sub_id) || `ajan-${messages.length}`,
    persona: metin(event.persona) || "yardimci",
    unvan: metin(event.title) || "Yardımcı",
    avatar: metin(event.avatar) || metin(event.persona) || "yardimci",
    renk: metin(event.color) || "gri",
    gorev: metin(event.task),
    durum: "calisiyor",
    adimlar: [],
    baslangic: Date.now(),
  };
  const grup = typeof event.group_size === "number" && event.group_size > 1 ? event.group_size : 1;
  const indeks = acikGrup(messages, grup);
  if (indeks < 0) {
    return [...messages, { rol: "ekip", metin: kart.unvan, ajanlar: [kart], grupBoyutu: grup }];
  }
  const guncel = [...messages];
  const grupMesaji = guncel[indeks];
  guncel[indeks] = { ...grupMesaji, ajanlar: [...(grupMesaji.ajanlar ?? []), kart] };
  return guncel;
}

/** Aynı paralel gruptan henüz dolmamış son ekip mesajı (yoksa -1). */
function acikGrup(messages: Mesaj[], grup: number): number {
  if (grup <= 1) return -1;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const mesaj = messages[index];
    if (mesaj.rol === "kullanici") return -1;
    if (mesaj.rol !== "ekip") continue;
    const dolu = (mesaj.ajanlar ?? []).length;
    return mesaj.grupBoyutu === grup && dolu < grup ? index : -1;
  }
  return -1;
}

function ajanBitti(messages: Mesaj[], event: Record<string, unknown>): Mesaj[] {
  const kimlik = metin(event.sub_id);
  return kartiGuncelle(messages, kimlik, (kart) => ({
    ...kart,
    durum: event.ok === false ? "yarim" : "bitti",
    ozet: metin(event.summary) || undefined,
    sureSn: typeof event.elapsed_s === "number" ? event.elapsed_s : undefined,
    cagriSayisi: typeof event.tool_calls === "number" ? event.tool_calls : undefined,
    adimlar: kart.adimlar.map((adim) => (adim.basladi ? { ...adim, basladi: false } : adim)),
  })) ?? messages;
}

function ajanAdimi(messages: Mesaj[], kimlik: string, event: Record<string, unknown>): Mesaj[] {
  const adim = olayAdimi(event);
  // Kimliği taşıyan olay ana bloğa ASLA düşmez: kartı yoksa (geç bağlanan
  // sekme) sessizce yutulur; ana turun adımlarına karışması daha kötüdür.
  if (!adim || adim.sonuc) return messages;
  return kartiGuncelle(messages, kimlik, (kart) => ({
    ...kart,
    adimlar: adimiEkle(kart.adimlar, adim),
  })) ?? messages;
}

function kartiGuncelle(
  messages: Mesaj[],
  kimlik: string,
  degistir: (kart: AjanKarti) => AjanKarti,
): Mesaj[] | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const mesaj = messages[index];
    if (mesaj.rol !== "ekip") continue;
    const ajanlar = mesaj.ajanlar ?? [];
    const sira = ajanlar.findIndex((kart) => kart.id === kimlik);
    if (sira < 0) continue;
    const yeni = [...ajanlar];
    yeni[sira] = degistir(ajanlar[sira]);
    const guncel = [...messages];
    guncel[index] = { ...mesaj, ajanlar: yeni };
    return guncel;
  }
  return null;
}
