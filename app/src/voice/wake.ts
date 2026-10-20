import { playHum, stopHum } from "./cues";
import { localVoiceReply } from "./localVoice";
/** Uyandırma yereldir; bekleme konuşmaları modele gönderilmez. */
export function routeWakeSpeech(text: string, awake: boolean): { awake: boolean; acknowledge: boolean; message: string | null } {
  const value = text.trim();
  if (localVoiceReply(value) && /(?:^|[\s,!.?:;])(?:fusion|füzyon|fuzyon)(?=$|[\s,!.?:;])/iu.test(value)) {
    return { awake: true, acknowledge: false, message: value };
  }
  const greeted = /^(?:merhaba|selam|hey)[,\s]+(?:fusion|füzyon|fuzyon)[,!.?:;\s]+(.+)$/iu.exec(value);
  if (greeted) return { awake: true, acknowledge: true, message: greeted[1].trim() };
  const wake = /^(?:fusion|füzyon|fuzyon)(?:[\s,!.?:;—-]+|$)/iu.exec(value);
  if (wake) return { awake: true, acknowledge: true, message: value.slice(wake[0].length).trim() || null };
  if (!awake || /^(?:hm|hmm|hımm)[.!?]*$/iu.test(value)) return { awake, acknowledge: false, message: null };
  return { awake, acknowledge: false, message: value || null };
}

export function speechFailureText(text: string): string {
  return /Siri and Dictation are disabled/i.test(text)
    ? "macOS Dikte kapalı. Sistem Ayarları → Klavye → Dikte’yi açıp karaktere yeniden tıkla. Sesle Denetim açıksa Dikte yerine onu kullanıyor olabilir."
    : text;
}

/** Sistem sesi kullanılır; model veya uzak ses hizmeti çağrılmaz. */
export function acknowledgeWake(onError?: (message: string) => void): void {
  if (!("speechSynthesis" in window)) throw new Error("Bu sistemde sesli uyandırma yanıtı kullanılamıyor.");
  const utterance = new SpeechSynthesisUtterance("Hm");
  utterance.lang = "tr-TR";
  utterance.rate = 0.9;
  utterance.onerror = () => onError?.("Uyandırma duyuldu fakat kısa sesli yanıt çalınamadı. Sistem ses çıkışını kontrol et.");
  window.speechSynthesis.speak(utterance);
}

/** Düşünme sırasında kullanıcı "takıldı mı?" diye merak etmesin: Web Audio ile üretilen kısa "hmm" (model sesi değil). */
export function speakThinkingCue(): void {
  playHum();
}

/** Düşünme "Hmm"i yarım kalmasın: asıl cevap başlarken bekleyen ipucunu sustur. */
export function cancelThinkingCue(): void {
  stopHum();
}
