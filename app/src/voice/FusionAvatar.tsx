import fusionCharacter from "../brand/character/fusion-abstract.png";
import "./FusionAvatar.css";
export type AvatarState = "idle" | "listening" | "thinking" | "talking" | "happy" | "approval";
const LABELS: Record<AvatarState, string> = {
  idle: "Fusion bekliyor", listening: "Fusion dinliyor", thinking: "Fusion düşünüyor",
  talking: "Fusion konuşuyor", happy: "Fusion mutlu", approval: "Fusion onay bekliyor",
};
/** Fusion'ın özgün ana karakteri; durum hareketleri CSS ve azaltılmış hareket tercihini izler. */
export function FusionAvatar({ scale = 2, state = "idle" }: { scale?: number; state?: AvatarState }) {
  return <div className="fusion-avatar" data-state={state} style={{ height: 168 * scale, width: 168 * scale }}>
    <span aria-hidden="true" className="fusion-avatar__glow" />
    <img alt={LABELS[state]} className="fusion-avatar__frame" src={fusionCharacter} draggable={false} />
  </div>;
}
