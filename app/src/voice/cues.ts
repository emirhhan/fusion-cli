/**
 * Minik seslendirmeler.
 *
 * Ses DOSYASI taşınmaz: kısa tonlar Web Audio ile üretilir. Sebebi hem boyut
 * hem tutarlılık — üretilen ton her cihazda aynı duyulur, dosya kod çözücüsüne
 * ve örnekleme hızına bağlı değildir.
 *
 * Sesler KISA ve SAKİN tutulur: her etkileşimde çalan uzun bir ton, birkaç
 * dakika sonra rahatsız eder.
 */

type Cue = "listen-start" | "listen-stop" | "thinking" | "done";

/** Ton tarifleri: (frekans Hz, süre sn, ses seviyesi). */
const CUES: Record<Cue, [number, number, number][]> = {
  // Yükselen ikili: "seni dinliyorum".
  "listen-start": [[520, 0.07, 0.05], [780, 0.09, 0.05]],
  // Alçalan ikili: "durdum".
  "listen-stop": [[700, 0.07, 0.04], [440, 0.09, 0.04]],
  // Tek kısa nokta: düşünmenin başladığını belli eder, tekrar etmez.
  thinking: [[620, 0.06, 0.03]],
  // Yumuşak kapanış.
  done: [[660, 0.08, 0.045], [880, 0.11, 0.045]],
};

let context: AudioContext | null = null;

function audioContext(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const Ctor = window.AudioContext ?? (window as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  // Bağlam bir kez kurulur: her seste yenisini açmak kaynak sızdırır.
  context ??= new Ctor();
  return context;
}

/**
 * Kısa bir ton çal. Ses kapalıysa ya da tarayıcı izin vermiyorsa SESSİZCE
 * geçilir: seslendirme bir süstür, akışı durdurmamalı.
 */
export function playCue(cue: Cue): void {
  const ctx = audioContext();
  if (!ctx) return;
  try {
    let offset = 0;
    for (const [freq, duration, gainValue] of CUES[cue]) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      const start = ctx.currentTime + offset;
      // Ani başlangıç/bitiş "tık" sesi üretir; zarf ile yumuşatılır.
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(gainValue, start + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
      osc.connect(gain).connect(ctx.destination);
      osc.start(start);
      osc.stop(start + duration + 0.02);
      offset += duration * 0.75;
    }
  } catch {
    // Otomatik oynatma engeli ya da kapalı ses aygıtı: sessizce geç.
  }
}

/** Azaltılmış hareket tercihi seslendirmeyi de kapatır. */
export function cuesEnabled(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return true;
  return !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
