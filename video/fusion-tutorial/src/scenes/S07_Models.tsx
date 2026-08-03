import React from "react";
import { SceneLayout } from "../components/SceneLayout";
import { Terminal, Line } from "../components/Terminal";
import { Bullet, Code } from "../components/primitives";
import { theme } from "../theme";

const lines: Line[] = [
  { kind: "comment", text: "canlı katalogdan model seç — profil rozetiyle", at: 0 },
  { kind: "cmd", text: "/development", at: 12 },
  { kind: "out", text: "Model seç — OpenRouter (ücretsiz):", at: 40, color: theme.dim },
  { kind: "out", text: "  llama-4-scout   131.072 token · profiller: low·medium·high·max", at: 52, color: theme.green },
  { kind: "out", text: "  küçük-model     32.000 token · profiller: low·medium", at: 66, color: theme.yellow },
  { kind: "gap", at: 0 },
  { kind: "cmd", text: "/model agent openrouter/…:free", at: 92 },
  { kind: "out", text: "agent → openrouter/…:free", at: 120, color: theme.green },
];

export const S07_Models: React.FC<{ i: number; n: number }> = ({ i, n }) => (
  <SceneLayout index={i} total={n} title="Model seçimi — /model & /development" align="center">
    <Terminal title="model" lines={lines} width={1440} />
    <Bullet delay={150} icon="▹" color={theme.accent}>
      Seçim ekranı, modelin <b>uygun olduğu profilleri</b> rozetler — küçük bağlamlı model
      üst profillerde görünmez. <Code>/model agent|judge|cand</Code> ile rol bazında değiştir.
    </Bullet>
  </SceneLayout>
);
