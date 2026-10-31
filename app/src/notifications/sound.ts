/**
 * Bildirim sesi: kısa, yumuşak bir çan (iki ton). Ses dosyası paketlenmez; Web Audio
 * ile üretilir, böylece paket büyümez ve CSP'ye medya kaynağı eklenmez.
 * Ses tercihi kapalıyken çağrılmaz (bkz. `useTurnNotifications`).
 */

interface SesBaglami {
  currentTime: number;
  destination: AudioNode;
  createOscillator(): OscillatorNode;
  createGain(): GainNode;
  close(): Promise<void>;
}

export const CHIME_DURATION_S = 0.18;

export function playChime(baglamOlustur: () => SesBaglami | null = varsayilanBaglam): void {
  let baglam: SesBaglami | null;
  try {
    baglam = baglamOlustur();
  } catch {
    return;
  }
  if (!baglam) return;
  const baslangic = baglam.currentTime;
  const kazanc = baglam.createGain();
  kazanc.gain.setValueAtTime(0.0001, baslangic);
  kazanc.gain.exponentialRampToValueAtTime(0.12, baslangic + 0.02);
  kazanc.gain.exponentialRampToValueAtTime(0.0001, baslangic + CHIME_DURATION_S * 2);
  kazanc.connect(baglam.destination);
  for (const [frekans, gecikme] of [[880, 0], [1174.66, CHIME_DURATION_S]] as const) {
    const osilator = baglam.createOscillator();
    osilator.type = "sine";
    osilator.frequency.setValueAtTime(frekans, baslangic + gecikme);
    osilator.connect(kazanc);
    osilator.start(baslangic + gecikme);
    osilator.stop(baslangic + gecikme + CHIME_DURATION_S);
  }
  window.setTimeout(() => {
    void baglam?.close().catch(() => undefined);
  }, CHIME_DURATION_S * 3 * 1000);
}

function varsayilanBaglam(): SesBaglami | null {
  const Ctor = (window as Window & { AudioContext?: new () => AudioContext; webkitAudioContext?: new () => AudioContext }).AudioContext
    ?? (window as Window & { webkitAudioContext?: new () => AudioContext }).webkitAudioContext;
  return Ctor ? new Ctor() : null;
}
