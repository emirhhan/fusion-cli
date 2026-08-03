import React from "react";
import { SceneLayout } from "../components/SceneLayout";
import { Terminal, Line } from "../components/Terminal";
import { RiseIn } from "../components/primitives";
import { theme } from "../theme";

const lines: Line[] = [
  { kind: "cmd", text: "fusion", at: 0 },
  { kind: "out", text: "Fusion CLI hazır — yaz ve Enter'a bas.", at: 26, color: theme.dim },
  { kind: "gap", at: 0 },
  { kind: "cmd", text: "src/app.py'deki login hatasını bul ve düzelt", at: 40 },
  { kind: "out", text: "▸ app.py okunuyor…  ▸ testler çalıştırılıyor…  ✓ düzeltildi", at: 120, color: theme.green },
];

const EngineCard: React.FC<{
  delay: number;
  name: string;
  color: string;
  desc: string;
}> = ({ delay, name, color, desc }) => (
  <RiseIn delay={delay}>
    <div
      style={{
        width: 560,
        padding: "28px 34px",
        borderRadius: 18,
        background: theme.surface,
        border: `1px solid ${color}55`,
        boxShadow: `0 20px 60px rgba(0,0,0,0.4)`,
      }}
    >
      <div style={{ fontFamily: theme.fontMono, fontSize: 40, color, fontWeight: 800 }}>
        /{name}
      </div>
      <div style={{ fontFamily: theme.fontSans, fontSize: 32, color: theme.text, marginTop: 12 }}>
        {desc}
      </div>
    </div>
  </RiseIn>
);

export const S04_Engines: React.FC<{ i: number; n: number }> = ({ i, n }) => (
  <SceneLayout index={i} total={n} title="İki motor: agent ve fusion" align="center">
    <Terminal title="ilk çalıştırma" lines={lines} width={1360} />
    <div style={{ display: "flex", gap: 40, marginTop: 10 }}>
      <EngineCard
        delay={150}
        name="agent"
        color={theme.accent}
        desc="Araçlarla İŞ YAPAR: dosya düzenler, komut çalıştırır, test eder."
      />
      <EngineCard
        delay={165}
        name="fusion"
        color={theme.blue}
        desc="Aynı soruyu birçok modele sorar, hakem + sentezle en iyisini verir."
      />
    </div>
  </SceneLayout>
);
