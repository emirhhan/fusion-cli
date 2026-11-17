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

/** Swift yardımcısının yapısal hata kodu (U2-10); eski yardımcı kod yazmaz, metne düşülür. */
export const DIKTE_KAPALI_KODU = "dikte_kapali";

/** Sistem Dikte/Siri kapalı mı? Önce yapısal koda bakılır, yoksa (eski yardımcı) sistem metnine. */
export function diktePasifMi(olay: { kod?: string; metin: string }): boolean {
  return olay.kod === DIKTE_KAPALI_KODU || /Siri and Dictation are disabled/i.test(olay.metin);
}

export function speechFailureText(text: string, kod?: string): string {
  return diktePasifMi({ kod, metin: text })
    ? "macOS Dikte kapalı. Sistem Ayarları → Klavye → Dikte’yi açıp karaktere yeniden tıkla. Sesle Denetim açıksa Dikte yerine onu kullanıyor olabilir."
    : text;
}

/** Uyandırma, kelime yerine yerel düşünme sesini çalar. */
export function acknowledgeWake(onError?: (message: string) => void): void {
  try { playHum(); }
  catch { onError?.("Kısa uyandırma sesi çalınamadı."); }
}

const thinkingPhrases = [
  [15_000, "Düşünüyorum."],
  [24_000, "Hâlâ düşünüyorum."],
  [30_000, "Bu soru biraz kafamı karıştırdı, düşünüyorum."],
] as const;

let cueUtterance: SpeechSynthesisUtterance | undefined;

function speakThinkingCue(text?: string): void {
  if (!text) { playHum(); return; }
  const speech = window.speechSynthesis;
  const voice = speech?.getVoices().find(candidate =>
    candidate.localService && candidate.lang.toLowerCase().startsWith("tr"),
  );
  if (!voice) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.voice = voice;
  utterance.lang = "tr-TR";
  utterance.rate = 0.9;
  utterance.onend = utterance.onerror = () => {
    if (cueUtterance === utterance) cueUtterance = undefined;
  };
  cueUtterance = utterance;
  speech.speak(utterance);
}

export function scheduleThinkingCues(play: (text?: string) => void = speakThinkingCue): () => void {
  const cue = (text?: string) => {
    try { play(text); } catch { /* Ses aygıtı yanıtı engellemesin. */ }
  };
  cue();
  const timers = [
    window.setTimeout(cue, 5_000),
    ...thinkingPhrases.map(([delay, text]) => window.setTimeout(() => cue(text), delay)),
    ...[45_000, 60_000, 75_000].map(delay => window.setTimeout(cue, delay)),
  ];
  return () => {
    timers.forEach(timer => window.clearTimeout(timer));
    stopHum();
    if (cueUtterance) {
      cueUtterance = undefined;
      window.speechSynthesis?.cancel();
    }
  };
}

export function isThinkingCueEcho(text: string): boolean {
  const normalize = (value: string) => value.toLocaleLowerCase("tr-TR")
    .replace(/â/gu, "a").replace(/[^\p{L}\s]/gu, "").trim();
  const heard = normalize(text);
  return thinkingPhrases.some(([, phrase]) => normalize(phrase) === heard);
}
