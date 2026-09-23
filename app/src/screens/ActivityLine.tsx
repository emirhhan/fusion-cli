import { useEffect, useRef, useState } from "react";
import type { OlayAdimi, OlaySonucu } from "../protocol/olayMetni";

/**
 * Çalışma göstergesi — tek satır, iş bitince kaybolur.
 *
 * Eskiden her tur bir "Çalışma / Çalışıyor / ✓ Tamamlandı" kutusu bırakıyordu:
 * "merhaba" gibi bir soruda bile cevabın üstünde yeşil tikli bir blok duruyordu
 * ve kullanıcı o bloğa basıp "2 adım" görüyordu. Gösterge artık DURUM bildirir,
 * başarı kutlamaz: çalışırken yanıp sönen bir satır, bitince hiçbir şey.
 *
 * Başarısızlık İSTİSNADIR ve kalıcıdır: iş yapılamadıysa kullanıcı bunu
 * görmeli, satırın sessizce kaybolması "oldu" izlenimi verirdi.
 */

type ActivityState = "running" | OlaySonucu;

/** Süre sayacının güncellenme aralığı (ms). */
const TICK_MS = 1000;

const SONUC_METNI: Record<Exclude<OlaySonucu, "completed">, string> = {
  failed: "Tamamlanamadı",
  partial: "Kısmen tamamlandı",
};

export function activityState(adimlar: OlayAdimi[]): ActivityState {
  return adimlar[adimlar.length - 1]?.sonuc ?? "running";
}

/** Blok çalışırken geçen saniye. Bitmiş blokta sayaç hiç kurulmaz. */
function useElapsedSeconds(running: boolean): number {
  const [seconds, setSeconds] = useState(0);
  const startedAt = useRef<number | null>(null);
  useEffect(() => {
    if (!running) {
      startedAt.current = null;
      setSeconds(0);
      return;
    }
    startedAt.current = Date.now();
    const timer = window.setInterval(() => {
      if (startedAt.current === null) return;
      setSeconds(Math.floor((Date.now() - startedAt.current) / TICK_MS));
    }, TICK_MS);
    return () => window.clearInterval(timer);
  }, [running]);
  return seconds;
}

function StepList({ adimlar }: { adimlar: OlayAdimi[] }) {
  return (
    <details className="activity__steps">
      <summary>{adimlar.length} adım · detaylar</summary>
      <ol>
        {adimlar.map((adim, index) => (
          // Alt ajan adımları ana turun adımlarıyla aynı listede durur ama
          // İŞARETLİDİR: kullanıcı hangi işi kimin yaptığını görebilmeli.
          // CLI'de bu ayrım `┌ alt-ajan` başlığıyla zaten vardı.
          <li data-sub-agent={adim.altAjan ? "true" : undefined} key={index}>
            {adim.altAjan && <span className="activity__step-badge">alt ajan</span>}
            <span className="activity__step-title">{adim.metin}</span>
            {adim.kaynak ? (
              <a href={adim.kaynak} rel="noreferrer noopener" target="_blank">{adim.kaynak}</a>
            ) : (
              adim.ayrinti && <span className="activity__step-detail">{adim.ayrinti}</span>
            )}
            {adim.dusunme && <pre className="activity__step-thinking">{adim.dusunme}</pre>}
          </li>
        ))}
      </ol>
    </details>
  );
}

export interface ActivityLineProps {
  adimlar: OlayAdimi[];
  /** Ayarlardaki "adımları göster" tercihi. */
  showSteps?: boolean;
}

export function ActivityLine({ adimlar, showSteps = false }: ActivityLineProps) {
  const durum = activityState(adimlar);
  const running = durum === "running";
  const seconds = useElapsedSeconds(running);
  const sonuncu = adimlar[adimlar.length - 1];

  if (running) {
    return (
      <div className="activity" data-state="running">
        <span className="activity__pulse">{sonuncu?.metin ?? "Çalışıyor"}</span>
        {seconds > 0 && <span className="activity__elapsed">{seconds} sn</span>}
      </div>
    );
  }

  // Tamamlanan iş iz bırakmaz; yalnız kullanıcı dökümü açık istediyse kalır.
  if (durum === "completed") {
    return showSteps && adimlar.length > 0 ? (
      <div className="activity" data-state="completed"><StepList adimlar={adimlar} /></div>
    ) : null;
  }

  // Canlı bölge YOK: duyuruyu `Conversation` tek bir yerden yapar. İkisi de
  // `role="status"` taşırken ekran okuyucu aynı sonucu iki kez okuyordu.
  return (
    <div className="activity" data-state={durum}>
      <span className="activity__result">{SONUC_METNI[durum]}</span>
      {sonuncu?.ayrinti && <span className="activity__detail">{sonuncu.ayrinti}</span>}
      {showSteps && adimlar.length > 0 && <StepList adimlar={adimlar} />}
    </div>
  );
}
