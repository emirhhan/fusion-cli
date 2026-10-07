import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

// Sahneyi yavaşça içeri iten "kamera": durağan slayt hissini kırar. Her sahneyi sar.
export const CameraPush: React.FC<{ children: React.ReactNode; from?: number; to?: number; drift?: number }> = ({
  children, from = 1, to = 1.08, drift = 30,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const p = frame / Math.max(1, durationInFrames);
  const scale = interpolate(p, [0, 1], [from, to]);
  return (
    <AbsoluteFill style={{ transform: `scale(${scale}) translate(${-drift * p}px, ${-drift * 0.4 * p}px)` }}>
      {children}
    </AbsoluteFill>
  );
};

// Derinlik katmanı: depth 0 = sabit, 1 = en çok hareket eden ön plan.
export const Parallax: React.FC<{ children: React.ReactNode; depth?: number }> = ({ children, depth = 0.5 }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ transform: `translate(${-frame * depth * 0.8}px, ${Math.sin(frame / 50) * 8 * depth}px)` }}>
      {children}
    </AbsoluteFill>
  );
};
