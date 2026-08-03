import React from "react";
import { SceneLayout } from "../components/SceneLayout";
import { Terminal, Line } from "../components/Terminal";
import { Bullet, Code } from "../components/primitives";
import { theme } from "../theme";

const lines: Line[] = [
  { kind: "cmd", text: "/providers", at: 0 },
  { kind: "out", text: "tanınan sağlayıcılar (tür · resmiyet · risk · durum):", at: 22, color: theme.dim },
  { kind: "out", text: "  OpenRouter    · aggregator · official_api · kurulu", at: 34, color: theme.green },
  { kind: "out", text: "  NVIDIA NIM    · api_key    · official_api · kurulu", at: 44, color: theme.green },
  { kind: "out", text: "  OpenAI/Gemini/Anthropic · api_key · official_api · anahtar yok", at: 54, color: theme.yellow },
  { kind: "out", text: "  Ollama        · local      · compatible   · yerel", at: 64, color: theme.blue },
  { kind: "out", text: "  ChatGPT/Gemini Web · web_session · disabled · framework (adaptör yok)", at: 74, color: theme.faint },
  { kind: "gap", at: 0 },
  { kind: "cmd", text: "/providers add", at: 100 },
  { kind: "out", text: "OpenAI anahtarını yapıştır (ekranda görünmez): ••••••••", at: 128, color: theme.dim },
  { kind: "out", text: "✓ OpenAI anahtarı şifreli kaydedildi. Sonraki oturumda etkin.", at: 150, color: theme.green },
];

export const S08_Providers: React.FC<{ i: number; n: number }> = ({ i, n }) => (
  <SceneLayout index={i} total={n} title="Sağlayıcılar — /providers" align="center">
    <Terminal title="providers" lines={lines} width={1500} />
    <Bullet delay={185} icon="🔒" color={theme.green}>
      <Code>/providers add</Code> anahtarı <b>getpass</b> ile alır, <b>şifreli</b> saklar
      (FUSION_SECRET_KEY ile) — anahtar log'a/ekrana girmez. Resmî API'ler kendi anahtarınla
      çalışır; web sağlayıcıları framework düzeyinde, kendi yetkili ucunla bağlanır.
    </Bullet>
  </SceneLayout>
);
