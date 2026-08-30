import { useEffect, useState } from "react";
import "./Spotlight.css";

/**
 * Arayüzdeki bir noktayı ışıkla göster.
 *
 * Derslerde EKRAN GÖRÜNTÜSÜ kullanılmadı: resim her arayüz değişiminde eskir
 * ve kullanıcı baktığı ekrandan farklı bir şey görür. Bunun yerine gerçek
 * öğenin üstü karartılmış bir katmandan kesilir ve yanına ok konur; gösterilen
 * şey her zaman kullanıcının o anki arayüzüdür.
 *
 * Öğe bulunamazsa hiçbir şey çizilmez: boş bir ışık halkası, olmayan bir
 * düğmeyi arattırırdı.
 */

/** Kesilen alanın çevresindeki nefes payı. */
const PAY = 8;

export interface SpotlightKutu {
  height: number;
  left: number;
  top: number;
  width: number;
}

/** İşaretli öğenin ekrandaki yerini ölç. Yoksa null. */
export function isaretKutusu(isaret: string, kok: ParentNode = document): SpotlightKutu | null {
  const hedef = kok.querySelector(`[data-ders="${isaret}"]`);
  if (!hedef || typeof (hedef as HTMLElement).getBoundingClientRect !== "function") return null;
  const kutu = (hedef as HTMLElement).getBoundingClientRect();
  if (kutu.width === 0 && kutu.height === 0) return null;
  return {
    height: kutu.height + PAY * 2,
    left: kutu.left - PAY,
    top: kutu.top - PAY,
    width: kutu.width + PAY * 2,
  };
}

export function Spotlight({
  isaret,
  metin,
  onClose,
}: {
  isaret: string;
  metin: string;
  onClose: () => void;
}) {
  const [kutu, setKutu] = useState<SpotlightKutu | null>(() => isaretKutusu(isaret));

  useEffect(() => {
    const olc = () => setKutu(isaretKutusu(isaret));
    olc();
    window.addEventListener("resize", olc);
    window.addEventListener("scroll", olc, true);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", olc);
      window.removeEventListener("scroll", olc, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [isaret, onClose]);

  if (!kutu) return null;

  // Balon öğenin altında durur; ekranın altına taşacaksa üstüne geçer.
  const altta = kutu.top + kutu.height + 120 < window.innerHeight;
  return (
    <div className="spotlight" onClick={onClose} role="presentation">
      <div
        className="spotlight__hole"
        style={{ height: kutu.height, left: kutu.left, top: kutu.top, width: kutu.width }}
      />
      <div
        className="spotlight__bubble"
        data-yon={altta ? "alt" : "ust"}
        style={{
          left: Math.max(12, Math.min(kutu.left, window.innerWidth - 300)),
          top: altta ? kutu.top + kutu.height + 12 : Math.max(12, kutu.top - 92),
        }}
      >
        <p>{metin}</p>
        <button onClick={onClose} type="button">Anladım</button>
      </div>
    </div>
  );
}
