import { useEffect, useState } from "react";
import "./ImageGenerationCard.css";

/**
 * Görsel üretilirken sohbette görünen yer tutucu (ChatGPT'deki gibi).
 *
 * Gerçek görsel gelene kadar, istenen en-boy oranında bir kutu ve canlı bir ışıltı gösterir;
 * kullanıcı işin sürdüğünü, neyin üretildiğini ve ne kadar beklediğini görür. Görsel gelince
 * bu kart kalkar, yerine cevabın içindeki görsel gelir.
 */

export interface ImageGenerationCardProps {
  prompt: string;
  /** "16:9" gibi; geçersizse 1:1. */
  aspect?: string;
}

function ratio(aspect: string): string {
  const match = /^(\d{1,2}):(\d{1,2})$/.exec(aspect);
  if (!match || Number(match[1]) === 0 || Number(match[2]) === 0) return "1 / 1";
  return `${match[1]} / ${match[2]}`;
}

/**
 * Sağlayıcılar gerçek ilerleme bildirmez; yüzde bir TAHMİNDİR: hızlı başlar, yavaşlar ve iş
 * bitmeden asla %97'yi geçmez. Görsel gelince kart zaten kalkar.
 */
const TYPICAL_SECONDS = 20;
const PROGRESS_CAP = 97;
const TICK_MS = 400;

export function estimatedPercent(elapsedSeconds: number): number {
  const value = 100 * (1 - Math.exp(-Math.max(0, elapsedSeconds) / TYPICAL_SECONDS));
  return Math.min(PROGRESS_CAP, Math.floor(value));
}

export function ImageGenerationCard({ prompt, aspect = "1:1" }: ImageGenerationCardProps) {
  const [percent, setPercent] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(
      () => setPercent(estimatedPercent((Date.now() - started) / 1000)),
      TICK_MS,
    );
    return () => window.clearInterval(timer);
  }, []);
  return (
    <figure
      aria-busy="true"
      aria-label="Görsel oluşturuluyor"
      className="image-generation"
      role="status"
    >
      <div className="image-generation__canvas" style={{ aspectRatio: ratio(aspect) }}>
        <div aria-hidden="true" className="image-generation__shimmer" />
        <div className="image-generation__label">
          <span aria-hidden="true" className="image-generation__spark">✦</span>
          <strong>Görsel oluşturuluyor…</strong>
          <b className="image-generation__percent">%{percent}</b>
        </div>
        <div
          aria-label="Tahmini ilerleme"
          aria-valuemax={100}
          aria-valuemin={0}
          aria-valuenow={percent}
          className="image-generation__bar"
          role="progressbar"
        >
          <span style={{ transform: `scaleX(${percent / 100})` }} />
        </div>
      </div>
      {prompt && <figcaption className="image-generation__prompt">{prompt}</figcaption>}
    </figure>
  );
}
