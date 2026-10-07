import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

// Sahne giriş/çıkışı: yakınlaşarak bulanıklıktan gelir, uzaklaşıp kararır. Her <Sequence>
// içeriğini bununla sar; `length` kare kadar giriş ve çıkış uygular.
export const SceneFade: React.FC<{ children: React.ReactNode; length?: number }> = ({ children, length = 14 }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const enter = interpolate(frame, [0, length], [0, 1], { extrapolateRight: "clamp" });
  const exit = interpolate(frame, [durationInFrames - length, durationInFrames], [1, 0], { extrapolateLeft: "clamp" });
  const v = Math.min(enter, exit);
  return (
    <AbsoluteFill style={{ opacity: v, filter: `blur(${(1 - v) * 16}px)`, transform: `scale(${1.06 - 0.06 * enter + (1 - exit) * 0.08})` }}>
      {children}
    </AbsoluteFill>
  );
};
