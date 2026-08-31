import type { Mesaj } from "../screens/Conversation";
import type { VoiceRuntimeState } from "./bridge";

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
