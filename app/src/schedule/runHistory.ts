import type { ScheduleClient, ScheduledTask } from "./types";

/** Kalıcı zamanlanmış görevin bir çalışması (`zamanlama.calisma_kaydet`, P-038). */
export interface ScheduleRun {
  zaman: number;
  sohbet_id: string;
  durum: "tamam" | "hata" | "onay_bekliyor";
  ozet: string;
}

interface RunMessage { rol: string; metin: string; hata?: boolean; ara?: boolean; akan?: boolean }

const OZET_KARAKTER = 240;

/** Çalışmanın sonucu: son nihai asistan cevabı (ara not ve akan balon sayılmaz). */
export function runOutcome(messages: readonly RunMessage[]): Pick<ScheduleRun, "durum" | "ozet"> {
  const son = [...messages].reverse().find((message) => message.rol === "asistan" && !message.ara && !message.akan);
  if (!son) return { durum: "hata", ozet: "Cevap üretilmedi." };
  const ozet = son.metin.replace(/\s+/g, " ").trim().slice(0, OZET_KARAKTER);
  return { durum: son.hata ? "hata" : "tamam", ozet };
}

/** Geçmişe yaz; başarısız kayıt çalışmayı bozmaz (yalnız geçmiş eksik kalır). */
export async function recordScheduleRun(
  client: ScheduleClient, task: ScheduledTask, sessionId: string, outcome: Pick<ScheduleRun, "durum" | "ozet">,
): Promise<boolean> {
  try {
    const result = await client.request("zamanlama.calisma_kaydet", { id: task.id, sohbet_id: sessionId, ...outcome });
    return result.ok === true;
  } catch {
    return false;
  }
}

/** Sonuç bildirimi metni. */
export function runNotice(task: ScheduledTask, outcome: Pick<ScheduleRun, "durum" | "ozet">): { baslik: string; metin: string } {
  return outcome.durum === "tamam"
    ? { baslik: "Zamanlanmış görev bitti", metin: `"${task.baslik}": ${outcome.ozet || "tamamlandı"}` }
    : { baslik: "Zamanlanmış görev hatayla bitti", metin: `"${task.baslik}": ${outcome.ozet}` };
}

/** Kayıttaki geçmişi doğrula; bozuk satır düşer. */
export function scheduleRuns(value: unknown): ScheduleRun[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item): ScheduleRun[] => {
    if (!item || typeof item !== "object") return [];
    const run = item as Record<string, unknown>;
    if (typeof run.zaman !== "number" || typeof run.sohbet_id !== "string") return [];
    if (run.durum !== "tamam" && run.durum !== "hata" && run.durum !== "onay_bekliyor") return [];
    return [{ zaman: run.zaman, sohbet_id: run.sohbet_id, durum: run.durum, ozet: typeof run.ozet === "string" ? run.ozet : "" }];
  });
}
