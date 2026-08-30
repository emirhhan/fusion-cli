import type { Mesaj } from "../screens/Conversation";
import type { VoiceRuntimeState } from "./bridge";

interface VoiceClient {
  request(name: string, data: Record<string, unknown>): Promise<Record<string, unknown>>;
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
): Promise<void> {
  await publish({ durum: "talking", metin: text });
  try {
    const result = await client.request("ses.konus", { bekle: true, metin: text });
    if (result.ok !== true || result.tamamlandi !== true) {
      await publish({
        durum: "error",
        metin: typeof result.metin === "string" ? result.metin : "Sesli yanıt tamamlanamadı.",
      });
      return;
    }
    await publish({ durum: "listening" });
  } catch (reason) {
    await publish({ durum: "error", metin: String(reason) });
  }
}
