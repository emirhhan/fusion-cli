import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { theme } from "./theme";

// 3B açıyla dönerek gelen cam kart. index ile sırayla gelir; ışık kenarı süzülür.
export const FeatureCard: React.FC<{ title: string; body?: string; icon?: string; index?: number; delay?: number; width?: number }> = ({
  title, body, icon, index = 0, delay = 0, width = 520,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - delay - index * 6, fps, config: { damping: 15, mass: 0.7 } });
  const shine = interpolate((frame - index * 6) % 120, [0, 120], [-100, 200]);
  return (
    <div style={{ perspective: 1400 }}>
      <div data-fusion-content={title} style={{
        boxSizing: "border-box", width, padding: "40px 44px", borderRadius: 28, position: "relative", overflow: "hidden",
        background: "linear-gradient(145deg, rgba(255,255,255,0.10), rgba(255,255,255,0.03))",
        border: "1.5px solid rgba(255,255,255,0.16)", boxShadow: `0 30px 80px rgba(0,0,0,0.45), 0 0 60px ${theme.accent2}22`,
        transform: `rotateY(${(1 - s) * 55}deg) translateY(${(1 - s) * 80}px) scale(${0.9 + 0.1 * s})`, opacity: s,
        fontFamily: theme.font, color: theme.text,
      }}>
        <div style={{ position: "absolute", inset: 0, background: `linear-gradient(110deg, transparent ${shine - 20}%, rgba(255,255,255,0.12) ${shine}%, transparent ${shine + 20}%)` }} />
        {icon && <div style={{ fontSize: 64, marginBottom: 18 }}>{icon}</div>}
        <div style={{ fontSize: 52, fontWeight: 750, letterSpacing: -1 }}>{title}</div>
        {body && <div style={{ fontSize: 34, color: theme.muted, marginTop: 14, lineHeight: 1.3 }}>{body}</div>}
      </div>
    </div>
  );
};
