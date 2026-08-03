import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { Background } from "../components/Background";
import { GradientText, RiseIn, Badge } from "../components/primitives";
import { theme } from "../theme";

export const S12_Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const pulse = 1 + 0.02 * Math.sin(frame / 12);
  return (
    <AbsoluteFill>
      <Background />
      <AbsoluteFill
        style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", gap: 34 }}
      >
        <RiseIn>
          <div style={{ transform: `scale(${pulse})` }}>
            <GradientText size={110}>Hazırsın.</GradientText>
          </div>
        </RiseIn>
        <RiseIn delay={14}>
          <div
            style={{
              fontFamily: theme.fontSans,
              fontSize: 44,
              color: theme.text,
              textAlign: "center",
              maxWidth: 1300,
            }}
          >
            <span style={{ fontFamily: theme.fontMono, color: theme.accent }}>fusion</span> yaz,
            görevini söyle — gerisini motorlar halleder.
          </div>
        </RiseIn>
        <RiseIn delay={26}>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap", justifyContent: "center", maxWidth: 1200 }}>
            {["/mode", "/effort", "/model", "/providers", "/health", "/plan", "/undo", "/good"].map(
              (c) => (
                <Badge key={c} color={theme.accent2}>
                  {c}
                </Badge>
              )
            )}
          </div>
        </RiseIn>
        <RiseIn delay={40}>
          <div style={{ fontFamily: theme.fontSans, fontSize: 30, color: theme.dim, marginTop: 20 }}>
            Ücretsiz · İki motorlu · Öz-öğrenen · Terminalde
          </div>
        </RiseIn>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
