import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { Background } from "../components/Background";
import { GradientText, RiseIn, Badge } from "../components/primitives";
import { theme } from "../theme";

export const S01_Intro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const glow = spring({ frame, fps, config: { damping: 200 } });
  const ring = interpolate(frame, [0, 90], [0.6, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill>
      <Background />
      <AbsoluteFill
        style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", gap: 30 }}
      >
        <div
          style={{
            width: 180,
            height: 180,
            borderRadius: 44,
            background: theme.gradient,
            transform: `scale(${glow}) rotate(${interpolate(frame, [0, 120], [0, 12])}deg)`,
            boxShadow: `0 0 ${80 * ring}px rgba(255,92,122,0.55)`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: theme.fontMono,
            fontSize: 110,
            fontWeight: 900,
            color: "#0b0b10",
          }}
        >
          ❯_
        </div>
        <RiseIn delay={12}>
          <GradientText size={130}>Fusion CLI</GradientText>
        </RiseIn>
        <RiseIn delay={22}>
          <div
            style={{
              fontFamily: theme.fontSans,
              fontSize: 46,
              color: theme.text,
              textAlign: "center",
              maxWidth: 1200,
            }}
          >
            Ücretsiz LLM'lerle çalışan, terminalde yaşayan agentic kodlama asistanı
          </div>
        </RiseIn>
        <RiseIn delay={34}>
          <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
            <Badge filled>Sıfırdan Eğitim</Badge>
            <Badge color={theme.blue}>İki Motor</Badge>
            <Badge color={theme.green}>Öz-öğrenen</Badge>
          </div>
        </RiseIn>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
