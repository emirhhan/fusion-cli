import hero from "../brand/pixel/hero.png";
import "./FusionAvatar.css";

/**
 * Fusion pixel karakteri — onaylı referans paketinden alınan kareler.
 *
 * Kareler YENİDEN ÇİZİLMEZ (bkz. paketteki `CLAUDE_HANDOFF.md`) ve
 * `image-rendering: pixelated` ile büyütülür; ara değerde ölçekleme pixel
 * art'ı bulanıklaştırır.
 *
 * ŞU AN TEK POZ KULLANILIYOR. Sebebi ölçüldü: paketteki altı ifade karesi
 * şeffaf DEĞİL (%0 saydam piksel) ve karakterin kendi yüz plakası ile arka
 * plan aynı siyah — (2,6,6) ve (0,0,0). Bu yüzden kesim yapılamıyor; kenardan
 * taşma-doldurma yüzü de siliyor. Yalnız `hero` karesi gerçekten şeffaf
 * (%67.7 saydam). İfadeler şeffaf hâlde gelirse durum eşlemesi buraya döner.
 */
export type AvatarState = "idle" | "listening" | "thinking" | "talking" | "happy";

export function FusionAvatar({ scale = 2, state = "idle" }: { scale?: number; state?: AvatarState }) {
  return (
    <div
      className="fusion-avatar"
      data-state={state}
      style={{ height: 82 * scale, width: 119 * scale }}
    >
      <img alt="" className="fusion-avatar__frame" src={hero} />
      <span aria-hidden="true" className="fusion-avatar__glow" />
    </div>
  );
}
