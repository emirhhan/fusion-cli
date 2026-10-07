import React, { useMemo } from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { seeded, theme } from "./theme";

// Yükselen ışık parçacıkları (derinlik hissi). count 40-120 arası iyi görünür.
export const Particles: React.FC<{ count?: number; color?: string; seed?: number }> = ({
  count = 70, color = theme.accent, seed = 7,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const dots = useMemo(() => {
    const r = seeded(seed);
    return Array.from({ length: count }, () => ({
      x: r() * width, y: r() * height, z: 0.3 + r() * 0.7, speed: 0.4 + r() * 1.2, phase: r() * 6.28,
    }));
  }, [count, seed, width, height]);
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {dots.map((d, i) => {
        const y = (((d.y - frame * d.speed * d.z * 2) % height) + height) % height;
        const x = d.x + Math.sin(frame / 40 + d.phase) * 20 * d.z;
        const s = 2 + d.z * 5;
        const flicker = 0.35 + 0.65 * Math.abs(Math.sin(frame / 25 + d.phase));
        return (
          <div key={i} style={{
            position: "absolute", left: x, top: y, width: s, height: s, borderRadius: "50%",
            background: color, opacity: d.z * flicker, boxShadow: `0 0 ${s * 4}px ${color}`,
          }} />
        );
      })}
    </AbsoluteFill>
  );
};
