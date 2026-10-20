/**
 * Mikrofon seviyesi.
 *
 * Dalga formu UYDURULMAZ: gerçek mikrofon seviyesinden okunur. Sahte bir
 * animasyon, kullanıcı konuşmadığında da oynardı ve panelin "sahte durduğu"
 * geri bildirimi tam olarak buydu.
 *
 * Tanımayı Swift yardımcısı yapar; buradaki akış YALNIZ görselleştirme
 * içindir. Mikrofon açılamazsa seviye 0 kalır ve çubuklar sakin durur.
 */

export interface LevelMeter {
  /** 0..1 arası anlık seviye. */
  read: () => number;
  stop: () => void;
}

export async function startLevelMeter(
  getMedia: () => Promise<MediaStream> = () =>
    navigator.mediaDevices.getUserMedia({ audio: true }),
): Promise<LevelMeter | null> {
  if (typeof window === "undefined") return null;
  const Ctor =
    window.AudioContext ??
    (window as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor || !navigator.mediaDevices) return null;
  try {
    const stream = await getMedia();
    const context = new Ctor();
    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const buffer = new Uint8Array(analyser.frequencyBinCount);

    return {
      read: () => {
        analyser.getByteTimeDomainData(buffer);
        // Ortalama karekök: tepe değeri tek bir çatırtıda zıplardı.
        let toplam = 0;
        for (const ornek of buffer) {
          const sapma = (ornek - 128) / 128;
          toplam += sapma * sapma;
        }
        return Math.min(1, Math.sqrt(toplam / buffer.length) * 3);
      },
      stop: () => {
        stream.getTracks().forEach((track) => track.stop());
        void context.close().catch(() => undefined);
      },
    };
  } catch {
    return null;
  }
}
