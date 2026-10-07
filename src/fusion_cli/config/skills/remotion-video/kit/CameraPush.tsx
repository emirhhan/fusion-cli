import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

// Sahneyi yavaşça içeri iten "kamera": durağan slayt hissini kırar. Her sahneyi sar.
export const CameraPush: React.FC<{ children: React.ReactNode; from?: number; to?: number; drift?: number }> = ({
  children, from = 1, to = 1.05, drift = 20,
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

// Derinlik katmanı: depth 0 = sabit, 1 = en çok hareket eden ön plan. Hareket SINIRLI bir
// salınımdır (en çok ±28 px): sürekli kayma içeriği ekran kenarından taşırıp kesiyordu.
export const Parallax: React.FC<{ children: React.ReactNode; depth?: number }> = ({ children, depth = 0.5 }) => {
  const frame = useCurrentFrame();
  const x = Math.sin(frame / 70) * 28 * depth;
  const y = Math.cos(frame / 55) * 10 * depth;
  return (
    <div style={{ position: "relative", flexShrink: 0, transform: `translate(${x}px, ${y}px)` }}>
      {children}
    </div>
  );
};
