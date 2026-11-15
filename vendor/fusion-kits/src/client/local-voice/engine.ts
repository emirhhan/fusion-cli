/** Sesli konuşmanın ses katmanı. Model turu sunucuda; burada yalnız dinleme
 * (konuşmayı metne çevirme) ve seslendirme var. İki uygulama:
 * - Fusion içinde: Fusion'ın cihaz içi tanıması (`fusion-listen`) ve yerel sesi
 *   (`say`/Piper) postMessage köprüsüyle — anahtarsız, metin ağa çıkmaz.
 * - Tarayıcıda: Web Speech API (`SpeechRecognition` + `speechSynthesis`). */
export interface ListenHandlers {
  onPartial(text: string): void;
  onFinal(text: string): void;
  onError(message: string): void;
}
export interface VoiceEngine {
  readonly kind: 'fusion' | 'browser';
  listen(handlers: ListenHandlers): Promise<void>;
  stopListening(): Promise<void>;
  /** Bitince ya da `stopSpeaking` ile kesilince çözülür. */
  speak(text: string): Promise<void>;
  stopSpeaking(): Promise<void>;
  close(): void;
}
export const NO_VOICE_MESSAGE =
  'Bu tarayıcıda sesli konuşma yok. Kits’i Fusion uygulamasında ya da Chrome’da aç.';
