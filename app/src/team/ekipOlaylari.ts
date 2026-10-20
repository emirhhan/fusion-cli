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

export type AjanDurumu = "calisiyor" | "bitti" | "yarim" | "iptal" | "butce";

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
  detayBekleniyor?: boolean;
  degisenYollar?: string[];
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

function ajanBasladi(messages: Mesaj[], event: Record<string, unknown>, placeholder = false): Mesaj[] {
  const kart: AjanKarti = {
    id: metin(event.sub_id) || `ajan-${messages.length}`,
    persona: metin(event.persona) || "yardimci",
    unvan: metin(event.title) || "Yardımcı",
    avatar: metin(event.avatar) || metin(event.persona) || "yardimci",
    renk: metin(event.color) || "gri",
    gorev: metin(event.task),
    durum: "calisiyor",
    adimlar: [],
    detayBekleniyor: placeholder,
    baslangic: typeof event.started_at === "number" && event.started_at > 0 ? event.started_at * 1000 : Date.now(),
  };
  const existing = messages.some((message) => message.ajanlar?.some((entry) => entry.id === kart.id));
  if (existing) return kartiGuncelle(messages, kart.id, (current) => current.detayBekleniyor
    ? { ...current, persona: kart.persona, unvan: kart.unvan, avatar: kart.avatar, renk: kart.renk, gorev: kart.gorev, baslangic: kart.baslangic, detayBekleniyor: false }
    : current) ?? messages;
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
  if (!kimlik) return messages;
  const finish = (kart: AjanKarti): AjanKarti => ({
    ...kart,
    durum: event.status === "cancelled" ? "iptal" : event.status === "budget" ? "butce" : event.ok === false ? "yarim" : "bitti",
    ozet: metin(event.summary) || undefined,
    sureSn: typeof event.elapsed_s === "number" ? event.elapsed_s : undefined,
    cagriSayisi: typeof event.tool_calls === "number" ? event.tool_calls : undefined,
    degisenYollar: Array.isArray(event.changed_paths) ? event.changed_paths.filter((path): path is string => typeof path === "string") : undefined,
    adimlar: kart.adimlar.map((adim) => (adim.basladi ? { ...adim, basladi: false } : adim)),
  });
  const updated = kartiGuncelle(messages, kimlik, finish);
  if (updated) return updated;
  const placeholder = ajanBasladi(messages, { sub_id: kimlik }, true);
  return kartiGuncelle(placeholder, kimlik, finish) ?? placeholder;
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

/** Yeni tur kabul edilirken önceki turun bitiş olayı eksik ajanlarını kapat. */
export function closeUnfinishedAgents(messages: Mesaj[]): Mesaj[] {
  return messages.map((message) => message.rol === "ekip" ? { ...message,
    ajanlar: message.ajanlar?.map((agent) => agent.durum === "calisiyor" ? { ...agent, durum: "yarim" as const } : agent),
  } : message);
}
