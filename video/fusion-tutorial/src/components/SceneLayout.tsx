import React from "react";
import { AbsoluteFill } from "remotion";
import { Background } from "./Background";
import { SceneHeader } from "./primitives";

// Ortak sahne iskeleti: atmosfer + üst başlık + ortalanmış içerik.
export const SceneLayout: React.FC<{
  index: number;
  total: number;
  title: string;
  children: React.ReactNode;
  align?: "center" | "flex-start";
}> = ({ index, total, title, children, align = "center" }) => (
  <AbsoluteFill>
    <Background />
    <AbsoluteFill style={{ padding: "72px 96px" }}>
      <SceneHeader index={index} total={total} title={title} />
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: align,
          gap: 34,
          marginTop: 24,
        }}
      >
        {children}
      </div>
    </AbsoluteFill>
  </AbsoluteFill>
);
