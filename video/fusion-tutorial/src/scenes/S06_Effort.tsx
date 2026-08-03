import React from "react";
import { SceneLayout } from "../components/SceneLayout";
import { Terminal, Line } from "../components/Terminal";
import { RiseIn, Badge, Code } from "../components/primitives";
import { theme } from "../theme";

const lines: Line[] = [
  { kind: "comment", text: "mode = HANGİ model  |  effort = NE KADAR düşünsün", at: 0 },
  { kind: "cmd", text: "/effort high", at: 20 },
  { kind: "out", text: "effort → high", at: 44, color: theme.green },
  { kind: "gap", at: 0 },
  { kind: "cmd", text: "/effort max", at: 60 },
  { kind: "out", text: "effort → max (model high olarak uygular)", at: 84, color: theme.yellow },
];

export const S06_Effort: React.FC<{ i: number; n: number }> = ({ i, n }) => (
  <SceneLayout index={i} total={n} title="Reasoning effort — /effort" align="center">
    <Terminal title="effort" lines={lines} width={1280} />
    <RiseIn delay={120}>
      <div style={{ display: "flex", gap: 14, marginTop: 8 }}>
        {["auto", "low", "medium", "high", "xhigh", "max"].map((e) => (
          <Badge key={e} color={e === "auto" ? theme.dim : theme.accent}>
            {e}
          </Badge>
        ))}
      </div>
    </RiseIn>
    <RiseIn delay={140}>
      <div
        style={{
          fontFamily: theme.fontSans,
          fontSize: 34,
          color: theme.text,
          textAlign: "center",
          maxWidth: 1300,
        }}
      >
        <b>mode ≠ effort.</b> Effort ayrı bir eksendir: model reasoning desteklemiyorsa
        parametre <Code>hiç gönderilmez</Code>; desteklemeyen <Code>xhigh/max</Code>{" "}
        en yakın seviyeye (high) iner ve bu sana bildirilir.
      </div>
    </RiseIn>
  </SceneLayout>
);
