import React from "react";
import { SceneLayout } from "../components/SceneLayout";
import { Terminal, Line } from "../components/Terminal";
import { RiseIn, Code } from "../components/primitives";
import { theme } from "../theme";

const lines: Line[] = [
  { kind: "cmd", text: "/mode", at: 0 },
  { kind: "out", text: "Çalışma profili seç:", at: 22, color: theme.dim },
  { kind: "out", text: "  auto   göreve göre kademe seç", at: 30, color: theme.accent },
  { kind: "out", text: "  low · medium · high · max", at: 40, color: theme.dim },
  { kind: "gap", at: 0 },
  { kind: "cmd", text: "/mode auto", at: 60 },
  { kind: "out", text: "auto profil → max  (karmaşıklık: mimari, tüm, yeniden tasarla)", at: 88, color: theme.green },
];

const rungs = [
  { name: "low", desc: "hızlı · ekonomik", color: theme.green },
  { name: "medium", desc: "dengeli (varsayılan)", color: theme.blue },
  { name: "high", desc: "zor debugging · mimari", color: theme.yellow },
  { name: "max", desc: "en yüksek kalite", color: theme.accent2 },
];

export const S05_Mode: React.FC<{ i: number; n: number }> = ({ i, n }) => (
  <SceneLayout index={i} total={n} title="Çalışma profilleri — /mode" align="center">
    <div style={{ display: "flex", gap: 56, alignItems: "center" }}>
      <Terminal title="mode" lines={lines} width={980} />
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {rungs.map((r, idx) => (
          <RiseIn key={r.name} delay={120 + idx * 12}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 20,
                width: 620,
                padding: "16px 24px",
                borderRadius: 14,
                background: theme.surface,
                borderLeft: `6px solid ${r.color}`,
                border: `1px solid ${theme.surfaceBorder}`,
              }}
            >
              <span
                style={{
                  fontFamily: theme.fontMono,
                  fontSize: 36,
                  fontWeight: 800,
                  color: r.color,
                  width: 150,
                }}
              >
                {r.name}
              </span>
              <span style={{ fontFamily: theme.fontSans, fontSize: 30, color: theme.text }}>
                {r.desc}
              </span>
            </div>
          </RiseIn>
        ))}
        <RiseIn delay={180}>
          <div style={{ fontFamily: theme.fontSans, fontSize: 28, color: theme.dim, marginTop: 8 }}>
            <Code>auto</Code> her turda görevi sınıflandırıp kademeyi kendi seçer.
          </div>
        </RiseIn>
      </div>
    </div>
  </SceneLayout>
);
