import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

// Ekranı çapraz geçen ışık şeridi. start: başlama karesi, duration: geçiş süresi (kare).
export const LightSweep: React.FC<{ start?: number; duration?: number; color?: string; angle?: number }> = ({
  start = 0, duration = 40, color = "rgba(255,255,255,0.22)", angle = 20,
}) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [start, start + duration], [-0.4, 1.4], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ pointerEvents: "none", mixBlendMode: "screen", overflow: "hidden" }}>
      <div style={{
        position: "absolute", top: "-50%", height: "200%", width: "22%", left: `${p * 100}%`,
        transform: `rotate(${angle}deg)`,
        background: `linear-gradient(90deg, transparent, ${color}, transparent)`, filter: "blur(18px)",
      }} />
    </AbsoluteFill>
  );
};
