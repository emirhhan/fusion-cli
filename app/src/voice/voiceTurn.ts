import type { Mesaj } from "../screens/Conversation";
import type { VoiceRuntimeState } from "./bridge";
import { splitIntoSentences } from "./sentenceStream";

interface VoiceClient {
  request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>>;
}

function errorText(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

export interface VoiceTurnHandle {
  id: string;
  cancel(): Promise<void>;
  finished: Promise<void>;
}

export function findVoiceAnswer(messages: Mesaj[], afterIndex: number): string | null {
  for (let index = messages.length - 1; index >= afterIndex; index -= 1) {
    const message = messages[index];
    if (message.rol === "asistan" && message.metin.trim()) return message.metin.trim();
  }
  return null;
}

/** Kısa selamlaşmalar model turu beklemeden aynı TTS hattından yanıtlanır. */
export function cannedVoiceAnswer(text: string): string | null {
  const normalized = text.toLocaleLowerCase("tr-TR")
    .replace(/ı/g, "i")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
  if (/^(merhaba|selam)( fusion)?$/.test(normalized)) return "merhabalar abi buyur";
  if (/^nasilsin( fusion)?$/.test(normalized)) {
    return "iyidir çok şükür sen nasılsın yok bir yaramazlık inşallah";
  }
  return null;
}

export async function speakVoiceAnswer(
  client: VoiceClient,
  text: string,
  publish: (state: VoiceRuntimeState) => Promise<void>,
): Promise<VoiceTurnHandle> {
  await publish({ durum: "talking", metin: text });
  try {
    const result = await client.request("ses.konus", { metin: text });
    const id = typeof result.tur_id === "string" ? result.tur_id : "";
    if (result.ok !== true || !id) {
      throw new Error(
        typeof result.metin === "string" ? result.metin : "Sesli yanıt başlatılamadı.",
      );
    }
    let cancelled = false;
    let settled = false;
    let cancellation: Promise<void> | null = null;
    const finished = client.request("ses.bekle", { tur_id: id }).then(async (completion) => {
      settled = true;
      if (cancelled) return;
      if (completion.ok !== true || completion.tamamlandi !== true) {
        throw new Error(
          typeof completion.metin === "string"
            ? completion.metin
            : "Sesli yanıt tamamlanamadı.",
        );
      }
      await publish({ durum: "listening" });
    }).catch(async (reason) => {
      settled = true;
      if (cancelled) return;
      await publish({ durum: "error", metin: errorText(reason) });
      throw reason;
    });

    return {
      id,
      finished,
      cancel: () => {
        if (cancellation) return cancellation;
        if (settled) return Promise.resolve();
        cancelled = true;
        const cancellationStartedAt = performance.now();
        cancellation = client.request("ses.durdur", { tur_id: id }).then(async (stopped) => {
          if (stopped.ok !== true) {
            throw new Error(
              typeof stopped.metin === "string" ? stopped.metin : "Sesli yanıt kesilemedi.",
            );
          }
          if (import.meta.env.DEV) {
            console.debug("[talk] TTS cancellation acknowledged", {
              elapsed_ms: performance.now() - cancellationStartedAt,
              tur_id: id,
            });
          }
          await publish({ durum: "interrupted" });
          await publish({ durum: "listening" });
        }).catch(async (reason) => {
          await publish({ durum: "error", metin: errorText(reason) });
          throw reason;
        });
        return cancellation;
      },
    };
  } catch (reason) {
    await publish({ durum: "error", metin: errorText(reason) });
    throw reason;
  }
}

/**
 * `speakVoiceAnswer` gibi ama TEK büyük TTS turu yerine cevabı cümlelere
 * bölüp AYRI turlar hâlinde art arda seslendirir.
 *
 * Neden: `ses.konus` tüm metni Piper'a TEK seferde verir ve konuşma ancak
 * TÜM metin sentezlendikten sonra başlar (bkz. `appserver/voice.py::speak`).
 * Uzun bir cevapta bu, kullanıcının sesi duymadan önce sentezin TAMAMINI
 * beklemesi demektir. Cümle cümle göndermek ilk sesin, YALNIZ ilk cümle
 * sentezlenince başlamasını sağlar; geri kalan cümleler bir öncekinin
 * çalması sürerken zaten sıradadır.
 *
 * `VoiceTurnHandle` sözleşmesi DEĞİŞMEZ: `cancel()` o an çalan cümleyi durdurup
 * kalan kuyruğu iptal eder, `finished` yalnız SON cümle bitince (ya da iptalde
 * hemen) çözülür — çağıran taraf (`SessionApplication.tsx`) tek bir tur
 * yönetiyormuş gibi davranmaya devam edebilir.
 */
export async function speakVoiceAnswerStreamed(
  client: VoiceClient,
  text: string,
  publish: (state: VoiceRuntimeState) => Promise<void>,
): Promise<VoiceTurnHandle> {
  await publish({ durum: "talking", metin: text });
  try {
    const sentences = splitIntoSentences(text);
    const queue = sentences.length > 0 ? sentences : [text];

    let cancelled = false;
    let settled = false;
    let cancellation: Promise<void> | null = null;
    let currentTurnId = "";

    const startSentence = async (sentence: string): Promise<string> => {
      const result = await client.request("ses.konus", { metin: sentence });
      const id = typeof result.tur_id === "string" ? result.tur_id : "";
      if (result.ok !== true || !id) {
        throw new Error(
          typeof result.metin === "string" ? result.metin : "Sesli yanıt başlatılamadı.",
        );
      }
      return id;
    };

    const waitSentence = async (id: string): Promise<void> => {
      const completion = await client.request("ses.bekle", { tur_id: id });
      // Bu bekleme `cancel()` tarafından KASITLI olarak kesilmiş olabilir;
      // o durumda `tamamlandi: false` bir hata değil, iptalin kendisidir.
      if (cancelled) return;
      if (completion.ok !== true || completion.tamamlandi !== true) {
        throw new Error(
          typeof completion.metin === "string"
            ? completion.metin
            : "Sesli yanıt tamamlanamadı.",
        );
      }
    };

    currentTurnId = await startSentence(queue[0]);

    const finished = (async () => {
      await waitSentence(currentTurnId);
      for (let index = 1; index < queue.length && !cancelled; index += 1) {
        currentTurnId = await startSentence(queue[index]);
        if (cancelled) break;
        await waitSentence(currentTurnId);
      }
    })().then(async () => {
      settled = true;
      if (cancelled) return;
      await publish({ durum: "listening" });
    }).catch(async (reason) => {
      settled = true;
      if (cancelled) return;
      await publish({ durum: "error", metin: errorText(reason) });
      throw reason;
    });

    return {
      id: currentTurnId,
      finished,
      cancel: () => {
        if (cancellation) return cancellation;
        if (settled) return Promise.resolve();
        cancelled = true;
        cancellation = client.request("ses.durdur", { tur_id: currentTurnId }).then(
          async (stopped) => {
            if (stopped.ok !== true) {
              throw new Error(
                typeof stopped.metin === "string" ? stopped.metin : "Sesli yanıt kesilemedi.",
              );
            }
            await publish({ durum: "interrupted" });
            await publish({ durum: "listening" });
          },
        ).catch(async (reason) => {
          await publish({ durum: "error", metin: errorText(reason) });
          throw reason;
        });
        return cancellation;
      },
    };
  } catch (reason) {
    await publish({ durum: "error", metin: errorText(reason) });
    throw reason;
  }
}
