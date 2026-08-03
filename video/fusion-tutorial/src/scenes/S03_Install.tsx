import React from "react";
import { SceneLayout } from "../components/SceneLayout";
import { Terminal, Line } from "../components/Terminal";
import { Bullet } from "../components/primitives";
import { theme } from "../theme";

const lines: Line[] = [
  { kind: "comment", text: "1) Projeyi al ve tek komutla kur", at: 0 },
  { kind: "cmd", text: "git clone <repo> && cd fusion-cli", at: 8 },
  { kind: "cmd", text: "make setup", at: 46 },
  { kind: "out", text: "✓ Python 3.11 bulundu — .venv kuruldu", at: 78, color: theme.green },
  { kind: "out", text: "✓ bağımlılıklar yüklendi, .env hazırlandı", at: 92, color: theme.green },
  { kind: "gap", at: 0 },
  { kind: "comment", text: "2) Ücretsiz anahtarı .env'e yaz (opsiyonel ama önerilir)", at: 108 },
  { kind: "cmd", text: "echo 'OPENROUTER_API_KEY=sk-...' >> .env", at: 118 },
];

export const S03_Install: React.FC<{ i: number; n: number }> = ({ i, n }) => (
  <SceneLayout index={i} total={n} title="Kurulum — tek komut" align="center">
    <Terminal title="kurulum" lines={lines} width={1360} />
    <Bullet delay={150} icon="✓" color={theme.green}>
      Anahtar yoksa da açılır; anahtar varsa modeller gerçekten yanıt verir.
    </Bullet>
  </SceneLayout>
);
