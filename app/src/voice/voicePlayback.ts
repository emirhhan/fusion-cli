import type { VoiceRuntimeState } from "./bridge";
import { splitIntoSpeechChunks } from "./sentenceStream";
import { speakVoiceAnswerStreamed, type VoiceTurnHandle } from "./voiceTurn";

interface VoiceClient {
  request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>>;
}

/** Oynayan cümlenin ardından gelen tek cümle hazırlanır; iptal tüm sahipliği kapatır. */
export function createVoicePlayback(
  client: VoiceClient, text: string, publish: (state: VoiceRuntimeState) => Promise<void>,
): VoiceTurnHandle {
  let cancelled = false;
  let settled = false;
  let cancellation: Promise<void> | null = null;
  let activeId: string | null = null;
  const stopping = new Map<string, Promise<void>>();
  const stopActive = async () => {
    const id = activeId;
    if (!id) return;
    let pending = stopping.get(id);
    if (!pending) {
      pending = client.request("ses.durdur", { tur_id: id }).then(result => {
        if (result.ok !== true) throw new Error("Sesli yanıt kesilemedi.");
        if (activeId === id) activeId = null;
      });
      stopping.set(id, pending);
    }
    await pending;
  };
  let starting: Promise<Record<string, unknown>> | null = null;
  let fallback: VoiceTurnHandle | null = null;
  const prepared = new Set<string>();
  const sentences = splitIntoSpeechChunks(text);
  const queue = sentences.length ? sentences : [text];
  const prepare = async (sentence: string) => {
    const result = await client.request("ses.hazirla", { metin: sentence });
    if (result.desteklenmiyor === true) return null;
    if (result.ok !== true || typeof result.hazir_id !== "string") {
      throw new Error(String(result.metin ?? "Ses hazırlanamadı."));
    }
    prepared.add(result.hazir_id);
    return result.hazir_id;
  };
  const cleanup = async () => {
    for (const id of prepared) {
      const result = await client.request("ses.haziri_sil", { hazir_id: id });
      if (result.ok !== true) throw new Error("Hazır ses temizlenemedi.");
      prepared.delete(id);
    }
  };
  let next: Promise<string | null> | null = prepare(queue[0]);
  // Ön yükleme reddi, çalan cümleyi beklerken yakalanmamış promise oluşturmaz.
  const observed = (promise: Promise<string | null>) => { void promise.catch(() => undefined); return promise; };
  observed(next);
  const finished = (async () => {
    try {
      for (let index = 0; index < queue.length && next; index += 1) {
        const id = await next;
        next = null;
        if (cancelled) break;
        if (id === null) {
          if (index !== 0) throw new Error("Ses hazırlama desteği konuşma sırasında değişti.");
          fallback = await speakVoiceAnswerStreamed(client, text, publish);
          if (cancelled) await fallback.cancel();
          await fallback.finished;
          return;
        }
        if (cancelled) break;
        starting = client.request("ses.haziri_cal", { hazir_id: id });
        const started = await starting;
        starting = null;
        if (started.ok !== true || typeof started.tur_id !== "string") {
          throw new Error(String(started.metin ?? "Hazır ses çalınamadı."));
        }
        prepared.delete(id);
        activeId = started.tur_id;
        if (cancelled) {
          await stopActive();
          break;
        }
        await publish({ durum: "talking", metin: text });
        if (index + 1 < queue.length) next = observed(prepare(queue[index + 1]));
        const completed = await client.request("ses.bekle", { tur_id: activeId });
        activeId = null;
        if (cancelled) break;
        if (completed.ok !== true || completed.tamamlandi !== true) {
          throw new Error(String(completed.metin ?? "Sesli yanıt tamamlanamadı."));
        }
      }
      if (!cancelled) await publish({ durum: "listening" });
    } catch (error) {
      if (!cancelled) {
        await publish({ durum: "error", metin: error instanceof Error ? error.message : String(error) });
        throw error;
      }
    } finally {
      try {
        try {
          await stopActive();
        } finally {
          if (next) await next.catch(() => undefined);
          await cleanup();
        }
      } finally { settled = true; }
    }
  })();
  return {
    id: crypto.randomUUID(), finished,
    cancel: () => {
      if (cancellation) return cancellation;
      if (settled) return Promise.resolve();
      cancelled = true;
      cancellation = (async () => {
        if (starting) await starting.catch(() => undefined);
        if (fallback) await fallback.cancel();
        await stopActive();
        await finished;
        await publish({ durum: "interrupted" });
        await publish({ durum: "listening" });
      })().catch(async (error) => {
        await publish({ durum: "error", metin: error instanceof Error ? error.message : String(error) });
        throw error;
      });
      return cancellation;
    },
  };
}
