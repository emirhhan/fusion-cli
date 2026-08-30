import { useEffect, useState } from "react";
import approval from "../brand/character/approval.png";
import blink from "../brand/character/blink.png";
import happy from "../brand/character/happy.png";
import idle from "../brand/character/idle.png";
import talkingA from "../brand/character/talking-a.png";
import talkingB from "../brand/character/talking-b.png";
import thinking from "../brand/character/thinking.png";
import "./FusionAvatar.css";

/**
 * Fusion karakterinin yüksek çözünürlüklü ifade kareleri.
 */
export type AvatarState = "idle" | "listening" | "thinking" | "talking" | "happy" | "approval";

const FRAMES: Record<AvatarState, string> = {
  idle,
  listening: idle,
  thinking,
  talking: talkingA,
  happy,
  approval,
};

const LABELS: Record<AvatarState, string> = {
  idle: "Fusion bekliyor",
  listening: "Fusion dinliyor",
  thinking: "Fusion düşünüyor",
  talking: "Fusion konuşuyor",
  happy: "Fusion mutlu",
  approval: "Fusion onay bekliyor",
};

/** Göz kırpma aralığı. Sabit ritim mekanik durur; rastgelelik canlı gösterir. */
const BLINK_MIN_MS = 2_800;
const BLINK_MAX_MS = 6_500;
const BLINK_DURATION_MS = 130;

/** Konuşurken ağız hareketi: konuşma ve boşta kareleri arasında gidip gelir. */
const TALK_FRAME_MS = 180;
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => window.matchMedia?.(REDUCED_MOTION_QUERY).matches ?? false);

  useEffect(() => {
    if (!window.matchMedia) return;
    const media = window.matchMedia(REDUCED_MOTION_QUERY);
    const update = () => setReduced(media.matches);
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);

  return reduced;
}

export function FusionAvatar({ scale = 2, state = "idle" }: { scale?: number; state?: AvatarState }) {
  const [blinking, setBlinking] = useState(false);
  const [secondTalkFrame, setSecondTalkFrame] = useState(false);
  const reducedMotion = usePrefersReducedMotion();

  useEffect(() => {
    setBlinking(false);
    if (reducedMotion || (state !== "idle" && state !== "listening" && state !== "happy")) return;
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
  }, [reducedMotion, state]);

  useEffect(() => {
    setSecondTalkFrame(false);
    if (state !== "talking" || reducedMotion) return;
    const timer = window.setInterval(() => setSecondTalkFrame((second) => !second), TALK_FRAME_MS);
    return () => window.clearInterval(timer);
  }, [reducedMotion, state]);

  const frame =
    blinking && (state === "idle" || state === "listening" || state === "happy")
      ? blink
      : state === "talking" && secondTalkFrame
        ? talkingB
        : FRAMES[state];

  return (
    <div className="fusion-avatar" data-state={state} style={{ height: 168 * scale, width: 168 * scale }}>
      <span aria-hidden="true" className="fusion-avatar__glow" />
      <img alt={LABELS[state]} className="fusion-avatar__frame" src={frame} />
    </div>
  );
}
