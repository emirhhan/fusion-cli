import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { theme } from "./theme";

// Kelime kelime (by="word") ya da harf harf yaylı giriş: bulanıklıktan netleşir, aşağıdan
// yükselir. delay: başlangıç karesi; stagger: parçalar arası kare. Başlık ≥ 96 px kullan.
export const KineticText: React.FC<{
  text: string; size?: number; delay?: number; stagger?: number; by?: "word" | "char";
  color?: string; weight?: number; gradient?: boolean; align?: "center" | "left";
}> = ({ text, size = 110, delay = 0, stagger = 3, by = "word", color = theme.text, weight = 800, gradient = false, align = "center" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const parts = by === "word" ? text.split(" ") : Array.from(text);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", justifyContent: align === "center" ? "center" : "flex-start",
      fontFamily: theme.font, fontSize: size, fontWeight: weight, letterSpacing: -size * 0.02, lineHeight: 1.05 }}>
      {parts.map((p, i) => {
        const s = spring({ frame: frame - delay - i * stagger, fps, config: { damping: 14, mass: 0.6 } });
        const blur = interpolate(s, [0, 1], [14, 0]);
        return (
          <span key={i} style={{
            display: "inline-block", whiteSpace: "pre", marginRight: by === "word" ? size * 0.25 : 0,
            transform: `translateY(${(1 - s) * size * 0.6}px) scale(${0.85 + 0.15 * s})`,
            opacity: s, filter: `blur(${blur}px)`,
            color: gradient ? "transparent" : color,
            backgroundImage: gradient ? `linear-gradient(100deg, ${theme.text}, ${theme.accent} 45%, ${theme.accent2})` : undefined,
            WebkitBackgroundClip: gradient ? "text" : undefined, backgroundClip: gradient ? "text" : undefined,
            textShadow: gradient ? undefined : `0 0 ${size * 0.4}px rgba(124,242,154,${0.25 * s})`,
          }}>{p}</span>
        );
      })}
    </div>
  );
};
