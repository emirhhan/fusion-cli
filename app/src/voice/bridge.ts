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

/**
 * Ses tercihleri köprüsü.
 *
 * Konuşma penceresinin kendi çekirdek bağlantısı YOKTUR: pencere hafif ve tek
 * amaçlı kalsın diye ayarlar ana pencere üzerinden uygulanır. Pencere ne
 * istediğini söyler, ana pencere `ses.ayar`/`ses.durum` çağırır ve sonucu geri
 * yayar. Böylece ayarın tek bir yazma yolu olur.
 */

export const VOICE_PREFS_REQUEST = "fusion://ses-ayar";
export const VOICE_PREFS_STATE = "fusion://ses-ayar-durum";

export interface VoicePrefsPayload {
  hiz: number;
  model: string | null;
  robotik: number;
}

/** Pencereden ana pencereye: bu tercihleri uygula (null ise yalnız oku). */
export async function requestVoicePrefs(
  prefs: VoicePrefsPayload | null,
  transport: Emitter = { emit: tauriEmit },
): Promise<void> {
  if (transport.emit === tauriEmit && !kabukVar()) return;
  await transport.emit(VOICE_PREFS_REQUEST, prefs);
}

/** Ana pencereden pencereye: geçerli tercihler. */
export async function publishVoicePrefs(
  prefs: VoicePrefsPayload,
  transport: Emitter = { emit: tauriEmit },
): Promise<void> {
  if (transport.emit === tauriEmit && !kabukVar()) return;
  await transport.emit(VOICE_PREFS_STATE, prefs);
}

function dinle<T>(
  event: string,
  handler: (payload: T) => void,
  transport: Listener,
): Promise<() => void> {
  if (transport.listen === (tauriListen as Listener["listen"]) && !kabukVar()) {
    return Promise.resolve(() => undefined);
  }
  return transport.listen(event, (received) => handler(received.payload as T));
}

export function onVoicePrefsRequest(
  handler: (prefs: VoicePrefsPayload | null) => void,
  transport: Listener = { listen: tauriListen as Listener["listen"] },
): Promise<() => void> {
  return dinle(VOICE_PREFS_REQUEST, handler, transport);
}

export function onVoicePrefsState(
  handler: (prefs: VoicePrefsPayload) => void,
  transport: Listener = { listen: tauriListen as Listener["listen"] },
): Promise<() => void> {
  return dinle(VOICE_PREFS_STATE, handler, transport);
}
