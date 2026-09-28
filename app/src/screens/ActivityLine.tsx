import { useEffect, useState } from "react";
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

/**
 * Blok çalışırken geçen saniye — TURUN BAŞLANGIÇ zamanından hesaplanır.
 *
 * `baslangicZamani` çağıran tarafından, oturumun mesaj durumunda saklanan
 * SABİT bir `Date.now()` damgasıdır (bkz. `olayAkisi.ts`). Eskiden bu zaman
 * yalnız bir `useRef` içinde tutuluyordu: kullanıcı başka bir sekmeye/sayfaya
 * gidip dönünce `ActivityLine` yeniden bağlanıyor, ref sıfırlanıyor ve sayaç
 * "25 sn" iken baştan "0 sn"ye dönüyordu. Başlangıç artık bileşenin DIŞINDA,
 * kalıcı durumda tutulduğu için yeniden bağlanma sayaçtan bağımsızdır.
 */
function useElapsedSeconds(running: boolean, baslangicZamani: number | undefined): number {
  const [, forceTick] = useState(0);
  useEffect(() => {
    if (!running || baslangicZamani === undefined) return;
    const timer = window.setInterval(() => forceTick((tick) => tick + 1), TICK_MS);
    return () => window.clearInterval(timer);
  }, [running, baslangicZamani]);
  if (!running || baslangicZamani === undefined) return 0;
  return Math.floor((Date.now() - baslangicZamani) / TICK_MS);
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

/** Araç adımının durumu için küçük işaret. */
const DURUM_ISARETI: Record<string, string> = { ok: "✓", failed: "✗", denied: "—", blocked: "—" };

/** Claude'daki gibi kalıcı adım izi: her araç tek soluk satır. */
function ToolTrail({ adimlar }: { adimlar: OlayAdimi[] }) {
  return (
    <ol className="activity__trail">
      {adimlar.map((adim, index) => (
        <li data-state={adim.durum ?? "running"} key={index}>
          <span className="activity__trail-text">{adim.metin}</span>
          {adim.durum && <span aria-hidden="true" className="activity__trail-mark">{DURUM_ISARETI[adim.durum] ?? ""}</span>}
        </li>
      ))}
    </ol>
  );
}

/** Biten işin özeti: "3 adım · src/app.py okunuyor ›" — tıklayınca açılır. */
function ToolSummary({ adimlar }: { adimlar: OlayAdimi[] }) {
  const son = adimlar[adimlar.length - 1];
  const baslik = adimlar.length === 1 ? son.metin : `${adimlar.length} adım · ${son.metin}`;
  return (
    <details className="activity__summary">
      <summary>{baslik}</summary>
      <ToolTrail adimlar={adimlar} />
    </details>
  );
}

export interface ActivityLineProps {
  /** Bu blok turun o an çalışan son bloğu mu? Değilse iz olarak çizilir. */
  aktif?: boolean;
  adimlar: OlayAdimi[];
  /** Bloğun başladığı sabit `Date.now()` damgası; oturum durumundan gelir. */
  baslangicZamani?: number;
  /** Ayarlardaki "adımları göster" tercihi. */
  showSteps?: boolean;
}

export function ActivityLine({ adimlar, aktif = true, baslangicZamani, showSteps = false }: ActivityLineProps) {
  const durum = activityState(adimlar);
  const running = durum === "running" && aktif;
  const seconds = useElapsedSeconds(running, baslangicZamani);
  const sonuncu = adimlar[adimlar.length - 1];
  // Yalnız araç adımları kalıcı iz bırakır; "düşünüyor" satırları geçicidir.
  const araclar = adimlar.filter((adim) => adim.arac);

  if (running) {
    const bitenler = sonuncu?.basladi ? araclar.slice(0, -1) : araclar;
    // Biten araç zaten izde durur; canlı satır onu tekrar etmez, modelin sıradaki
    // adımı düşündüğünü söyler.
    const canli = sonuncu && (sonuncu.basladi || !sonuncu.arac) ? sonuncu.metin : "Düşünüyor";
    return (
      <div className="activity" data-state="running">
        {bitenler.length > 0 && <ToolTrail adimlar={bitenler} />}
        <div className="activity__now">
          <span className="activity__pulse">{canli ?? "Çalışıyor"}</span>
          {seconds > 0 && <span className="activity__elapsed">{seconds} sn</span>}
        </div>
      </div>
    );
  }

  // Biten iş Claude'daki gibi soluk bir özet satırı bırakır; tıklayınca adımlar açılır.
  if (durum === "completed" || durum === "running") {
    if (showSteps && adimlar.length > 0) {
      return <div className="activity" data-state="completed"><StepList adimlar={adimlar} /></div>;
    }
    return araclar.length > 0 ? (
      <div className="activity" data-state="completed"><ToolSummary adimlar={araclar} /></div>
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
