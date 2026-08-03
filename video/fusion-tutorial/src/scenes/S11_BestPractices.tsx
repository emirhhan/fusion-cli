import React from "react";
import { SceneLayout } from "../components/SceneLayout";
import { Bullet, Code } from "../components/primitives";
import { theme } from "../theme";

export const S11_BestPractices: React.FC<{ i: number; n: number }> = ({ i, n }) => (
  <SceneLayout index={i} total={n} title="En verimli kullanım" align="flex-start">
    <div style={{ display: "flex", flexDirection: "column", gap: 26, maxWidth: 1560 }}>
      <Bullet delay={6} icon="1" color={theme.accent}>
        Günlük işte <Code>/mode auto</Code> aç — Fusion basit işe low, mimariye max seçer.
      </Bullet>
      <Bullet delay={18} icon="2" color={theme.blue}>
        Riskli/büyük değişiklikten önce <Code color={theme.blue}>/plan</Code> ile planı gör,
        sonra uygula.
      </Bullet>
      <Bullet delay={30} icon="3" color={theme.green}>
        Zor kararda <Code color={theme.green}>/fusion</Code> motoruna geç: birçok model +
        hakem daha güvenilir.
      </Bullet>
      <Bullet delay={42} icon="4" color={theme.yellow}>
        Reasoning modelinde <Code color={theme.yellow}>/effort high</Code> kaliteyi artırır;
        basit işte <Code color={theme.yellow}>low</Code> hız ve kotayı korur.
      </Bullet>
      <Bullet delay={54} icon="5" color={theme.accent2}>
        Sonuçtan memnunsan <Code color={theme.accent2}>/good</Code>, değilsen{" "}
        <Code color={theme.accent2}>/bad</Code> — Fusion öğrenir ve zamanla senin için iyileşir.
      </Bullet>
      <Bullet delay={66} icon="6" color={theme.dim}>
        Bir şey ters giderse <Code>/health</Code> ile sağlığı, <Code>/undo</Code> ile geri
        almayı hatırla.
      </Bullet>
    </div>
  </SceneLayout>
);
