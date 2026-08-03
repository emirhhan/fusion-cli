import React from "react";
import { SceneLayout } from "../components/SceneLayout";
import { Terminal, Line } from "../components/Terminal";
import { Bullet, Code } from "../components/primitives";
import { theme } from "../theme";

const lines: Line[] = [
  { kind: "cmd", text: "/health", at: 0 },
  { kind: "out", text: "sağlayıcı sağlığı (güvenilirlik · devre):", at: 22, color: theme.dim },
  { kind: "out", text: "  nvidia_nim/nemotron-super   · 98% · kapalı", at: 34, color: theme.green },
  { kind: "out", text: "  openrouter/gpt-oss-20b:free · 71% · AÇIK (atlanıyor)", at: 46, color: theme.red },
  { kind: "out", text: "  openrouter/…:free           · 95% · yarı-açık", at: 58, color: theme.yellow },
];

export const S09_Health: React.FC<{ i: number; n: number }> = ({ i, n }) => (
  <SceneLayout index={i} total={n} title="Otomatik sağlamlık — /health" align="center">
    <Terminal title="health" lines={lines} width={1360} />
    <Bullet delay={100} icon="⚡" color={theme.accent}>
      <b>Circuit breaker:</b> arka arkaya hata veren model devresi <Code>AÇIK</Code> olur ve
      bir süre atlanır — ölü modeli her turda yeniden yoklayıp seni bekletmez.
    </Bullet>
    <Bullet delay={118} icon="📈" color={theme.green}>
      <b>Güvenilirlik skoru</b> zamanla öğrenir; kısa arıza modeli kalıcı kötü saymaz.
    </Bullet>
  </SceneLayout>
);
