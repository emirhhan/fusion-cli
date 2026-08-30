import { emit as tauriEmit } from "@tauri-apps/api/event";
import { listen as tauriListen } from "@tauri-apps/api/event";

/**
 * Konuşma penceresi ile ana pencere arasındaki köprü.
 *
 * Konuşulan her şey ana penceredeki AYNI sohbete yazılır. Ayrı bir "ses
 * geçmişi" tutmak aynı konuşmayı iki yere bölerdi: kullanıcı kipi kapattığında
 * yazışmış gibi tam dökümü görmeli.
 *
 * Taşıma dışarıdan verilebilir; testler gerçek pencere olmadan sınanabilsin.
 */

export const VOICE_EVENT = "fusion://ses-mesaji";

export interface VoiceMessage {
  /** "kullanici": konuşulan söz. "asistan": Fusion'ın sesli cevabı. */
  kaynak: "kullanici" | "asistan";
  metin: string;
}

interface Emitter {
  emit: (event: string, payload: unknown) => Promise<void> | void;
}

interface Listener {
  listen: (
    event: string,
    handler: (event: { payload: unknown }) => void,
  ) => Promise<() => void>;
}

/** Tauri kabuğu var mı? Tarayıcıda (ve testte) olay köprüsü yoktur. */
export function kabukVar(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function emitVoiceMessage(
  message: VoiceMessage,
  transport: Emitter = { emit: tauriEmit },
): Promise<void> {
  // Boş söz gönderilmez: tanıma sessizlikte boş dize döndürebilir ve sohbete
  // boş bir mesaj düşmesi kullanıcıyı yanıltır.
  if (!message.metin.trim()) return;
  if (transport.emit === tauriEmit && !kabukVar()) return;
  await transport.emit(VOICE_EVENT, message);
}

export function onVoiceMessage(
  handler: (message: VoiceMessage) => void,
  transport: Listener = { listen: tauriListen as Listener["listen"] },
): Promise<() => void> {
  // Kabuk yoksa dinleme kurulamaz. Denemek, uygulama açılışında yakalanmayan
  // bir reddedilmiş söz üretir; sessizce boş bir sökücü döndürmek doğrusudur.
  if (transport.listen === (tauriListen as Listener["listen"]) && !kabukVar()) {
    return Promise.resolve(() => undefined);
  }
  return transport.listen(VOICE_EVENT, (event) => handler(event.payload as VoiceMessage));
}
