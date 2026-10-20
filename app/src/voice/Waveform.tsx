import { useEffect, useRef, useState } from "react";
import { startLevelMeter, type LevelMeter } from "./level";

/**
 * Dalga formu.
 *
 * Çubuklar GERÇEK mikrofon seviyesinden beslenir. Mikrofon açılamazsa (izin
 * yok, aygıt yok) hiçbir şey oynamaz: sahte hareket, dinlenmeyen bir mikrofonu
 * dinleniyor gibi gösterirdi.
 */

const BAR_COUNT = 9;
/** Ekran tazeleme hızına yakın ama daha ucuz: gözle akıcı görünen alt sınır. */
const TICK_MS = 60;

export function Waveform({
  active,
  baslat = startLevelMeter,
}: {
  active: boolean;
  baslat?: typeof startLevelMeter;
}) {
  const [bars, setBars] = useState<number[]>(() => Array(BAR_COUNT).fill(0));
  const meter = useRef<LevelMeter | null>(null);

  useEffect(() => {
    if (!active) {
      setBars(Array(BAR_COUNT).fill(0));
      return;
    }
    let alive = true;
    let timer: number | undefined;
    void baslat().then((olcer) => {
      if (!alive) {
        olcer?.stop();
        return;
      }
      meter.current = olcer;
      if (!olcer) return;
      timer = window.setInterval(() => {
        const seviye = olcer.read();
        // Yeni değer sağdan girer, eskiler sola kayar: konuşma akışı görünür.
        setBars((current) => [...current.slice(1), seviye]);
      }, TICK_MS);
    });
    return () => {
      alive = false;
      if (timer !== undefined) window.clearInterval(timer);
      meter.current?.stop();
      meter.current = null;
    };
  }, [active, baslat]);

  return (
    <div aria-hidden="true" className="voice-wave" data-active={active}>
      {bars.map((seviye, index) => (
        <span
          className="voice-wave__bar"
          key={index}
          style={{ transform: `scaleY(${0.12 + seviye * 0.88})` }}
        />
      ))}
    </div>
  );
}
