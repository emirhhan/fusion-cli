import React from "react";
import { SceneLayout } from "../components/SceneLayout";
import { RiseIn, Code } from "../components/primitives";
import { theme } from "../theme";

const cards = [
  { cmd: "/plan", color: theme.blue, title: "Plan modu", desc: "Önce oku ve planla; dosya değiştirmez. Onaylayınca uygular." },
  { cmd: "/undo", color: theme.yellow, title: "Geri al", desc: "Son turun dosya değişikliklerini tek komutla geri alır." },
  { cmd: "/verify", color: theme.green, title: "Doğrulama", desc: "Değişiklikten sonra test/lint çalışır; başarı iddiası kanıta bağlanır." },
  { cmd: "/good · /bad", color: theme.accent2, title: "Bellek", desc: "Geri bildirimin öğrenilir; benzer görevlerde daha iyi model seçilir." },
];

export const S10_Safety: React.FC<{ i: number; n: number }> = ({ i, n }) => (
  <SceneLayout index={i} total={n} title="Güvenlik, geri alma ve öğrenme" align="center">
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, width: 1500 }}>
      {cards.map((c, idx) => (
        <RiseIn key={c.cmd} delay={10 + idx * 14}>
          <div
            style={{
              padding: "30px 36px",
              borderRadius: 18,
              background: theme.surface,
              border: `1px solid ${theme.surfaceBorder}`,
              borderTop: `4px solid ${c.color}`,
            }}
          >
            <div style={{ fontFamily: theme.fontMono, fontSize: 36, color: c.color, fontWeight: 800 }}>
              {c.cmd}
            </div>
            <div style={{ fontFamily: theme.fontSans, fontSize: 30, color: theme.text, marginTop: 10 }}>
              <b>{c.title}.</b> {c.desc}
            </div>
          </div>
        </RiseIn>
      ))}
    </div>
    <RiseIn delay={80}>
      <div style={{ fontFamily: theme.fontSans, fontSize: 30, color: theme.dim }}>
        Yıkıcı komutlarda (<Code>rm -rf</Code>) Fusion önce durur ve onay ister.
      </div>
    </RiseIn>
  </SceneLayout>
);
