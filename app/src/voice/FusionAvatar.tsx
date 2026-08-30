import { useEffect, useState } from "react";
import blink from "../brand/pixel/blink.png";
import focus from "../brand/pixel/focus.png";
import happy from "../brand/pixel/happy.png";
import idle from "../brand/pixel/idle.png";
import talking from "../brand/pixel/talking.png";
import thinking from "../brand/pixel/thinking.png";
import "./FusionAvatar.css";

/**
 * Fusion pixel karakteri.
 *
 * Kareler onaylı paketten gelir ve YENİDEN ÇİZİLMEZ: 168×168, gerçekten
 * şeffaf ve karakterin kendi koyu yüz plakası korunmuş. `image-rendering:
 * pixelated` ile büyütülür; ara değerde ölçekleme pixel art'ı bulanıklaştırır.
 *
 * Canlılık iki kaynaktan gelir: kare değişimi (ifade) ve dönüşüm animasyonu
 * (süzülme, dönme). İkisi ayrı tutulur ki bir ifade değişimi hareketi
 * sıfırlamasın.
 */
export type AvatarState = "idle" | "listening" | "thinking" | "talking" | "happy";

const FRAMES: Record<AvatarState, string> = {
  idle,
  listening: focus,
  thinking,
  talking,
  happy,
};

/** Göz kırpma aralığı. Sabit ritim mekanik durur; rastgelelik canlı gösterir. */
const BLINK_MIN_MS = 2_800;
const BLINK_MAX_MS = 6_500;
const BLINK_DURATION_MS = 130;

/** Konuşurken ağız hareketi: konuşma ve boşta kareleri arasında gidip gelir. */
const TALK_FRAME_MS = 180;

export function FusionAvatar({ scale = 2, state = "idle" }: { scale?: number; state?: AvatarState }) {
  const [blinking, setBlinking] = useState(false);
  const [mouthOpen, setMouthOpen] = useState(true);

  // Göz kırpma yalnız sakin durumlarda: konuşurken ya da düşünürken karakterin
  // kendi karesi zaten değişiyor, üstüne kırpma koymak titreme gibi durur.
  useEffect(() => {
    if (state !== "idle" && state !== "happy") return;
    let timer: number;
    const schedule = () => {
      const delay = BLINK_MIN_MS + Math.random() * (BLINK_MAX_MS - BLINK_MIN_MS);
      timer = window.setTimeout(() => {
        setBlinking(true);
        window.setTimeout(() => {
          setBlinking(false);
          schedule();
        }, BLINK_DURATION_MS);
      }, delay);
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, [state]);

  // Konuşurken ağız açılıp kapanır; sessizken açık kalmaz.
  useEffect(() => {
    if (state !== "talking") {
      setMouthOpen(true);
      return;
    }
    const timer = window.setInterval(() => setMouthOpen((open) => !open), TALK_FRAME_MS);
    return () => window.clearInterval(timer);
  }, [state]);

  const frame =
    blinking && (state === "idle" || state === "happy")
      ? blink
      : state === "talking" && !mouthOpen
        ? idle
        : FRAMES[state];

  return (
    <div className="fusion-avatar" data-state={state} style={{ height: 168 * scale, width: 168 * scale }}>
      <span aria-hidden="true" className="fusion-avatar__glow" />
      <img alt="" className="fusion-avatar__frame" src={frame} />
    </div>
  );
}
