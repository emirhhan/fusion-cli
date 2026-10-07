import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { theme } from "./theme";

// Yavaşça akan, ışıklı renk lekeleri: düz zemin yerine her sahnenin arkasına koy.
export const Aurora: React.FC<{ colors?: string[]; intensity?: number }> = ({
  colors = [theme.accent2, theme.accent3, theme.accent],
  intensity = 0.55,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const t = frame / 30;
  return (
    <AbsoluteFill style={{ background: `radial-gradient(120% 90% at 50% 110%, ${theme.bg2}, ${theme.bg})`, overflow: "hidden" }}>
      {colors.map((c, i) => {
        const x = width * (0.5 + 0.35 * Math.sin(t * 0.35 + i * 2.1));
        const y = height * (0.5 + 0.3 * Math.cos(t * 0.28 + i * 1.7));
        const size = width * (0.55 + 0.1 * Math.sin(t * 0.5 + i));
        return (
          <div key={i} style={{
            position: "absolute", left: x - size / 2, top: y - size / 2, width: size, height: size,
            borderRadius: "50%", background: c, opacity: intensity * interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" }),
            filter: `blur(${width * 0.09}px)`, mixBlendMode: "screen",
          }} />
        );
      })}
      <AbsoluteFill style={{ background: "radial-gradient(70% 70% at 50% 50%, transparent 40%, rgba(0,0,0,0.65))" }} />
    </AbsoluteFill>
  );
};
