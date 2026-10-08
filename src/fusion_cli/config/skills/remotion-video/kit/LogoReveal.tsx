import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { theme } from "./theme";
import { useTimelineScene } from "./SceneContext";

// Logo açılışı: halka patlaması + ölçek/dönme yayı + parlama. src: public/ altındaki dosya.
export const LogoReveal: React.FC<{ src: string; size?: number; delay?: number; title?: string; subtitle?: string }> = ({
  src, size = 260, delay = 0, title, subtitle,
}) => {
  const isTimelineScene = useTimelineScene();
  const frame = useCurrentFrame() - delay;
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 11, mass: 0.8 } });
  const ring = interpolate(frame, [0, 40], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const glow = 0.5 + 0.5 * Math.sin(frame / 12);
  const ts = spring({ frame: frame - 18, fps, config: { damping: 16 } });
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
      <div style={{ position: "relative", width: size, height: size, display: "flex", alignItems: "center", justifyContent: "center" }}>
        {[0, 1, 2].map((i) => {
          const r = interpolate(ring, [0, 1], [0.2, 2.6 + i * 0.5]);
          return <div key={i} style={{
            position: "absolute", inset: 0, borderRadius: "50%",
            border: `3px solid ${i % 2 ? theme.accent2 : theme.accent}`, transform: `scale(${r})`,
            opacity: (1 - ring) * 0.8,
          }} />;
        })}
        <div style={{ filter: `drop-shadow(0 0 ${40 + 40 * glow}px ${theme.accent}aa)`,
          transform: `scale(${isTimelineScene ? 1 : s}) rotate(${(1 - s) * -25}deg)` }}>
          <Img data-fusion-content="Logo" src={staticFile(src)} style={{ width: size, height: size, borderRadius: size * 0.22 }} />
        </div>
      </div>
      {title && <div data-fusion-content={title} style={{ marginTop: 48, fontFamily: theme.font, fontSize: 120, fontWeight: 800, color: theme.text,
        letterSpacing: -2, opacity: isTimelineScene ? 1 : ts, transform: `translateY(${(1 - ts) * 40}px)` }}>{title}</div>}
      {subtitle && <div data-fusion-content={subtitle} style={{ marginTop: 16, fontFamily: theme.font, fontSize: 44, color: theme.muted,
        opacity: interpolate(frame, [30, 50], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>{subtitle}</div>}
    </AbsoluteFill>
  );
};
