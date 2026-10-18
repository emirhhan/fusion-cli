import React from "react";
import { createRoot } from "react-dom/client";
import { Conversation, type Mesaj } from "../src/screens/Conversation";
import "../src/theme/tokens.css";
import "../src/brand/brand.css";
import "../src/App.css";

const params = new URLSearchParams(location.search);
document.documentElement.dataset.theme = params.get("theme") ?? "dark";
const running = params.get("running") === "1";
const messages: Mesaj[] = [
  { id: "user", rol: "kullanici", metin: "Projeyi kaldığın yerden geliştir ve testleri çalıştır." },
  ...Array.from({ length: 24 }, (_, index): Mesaj => ({
    id: `note-${index}`, rol: "asistan", ara: true,
    metin: index === 0
      ? "Önceki araç sonucunu inceliyorum.\n\nDosyanın içeriğini doğrulayıp yalnız gerekli bölümü değiştireceğim.\n\n```bash\npython -m pytest\n```"
      : `Adım ${index + 1}: mevcut dosyayı okuyup ilgili düzeltmeyi doğruluyorum.`,
  })),
  ...(running ? [] : [{ id: "answer", rol: "asistan" as const, metin: "İş durduruldu. Yapılan değişiklikler ve araç sonuçları korundu; devam ettiğinde kalan testten sürdürebilirim." }]),
];
createRoot(document.getElementById("root")!).render(
  <main style={{ display: "flex", flexDirection: "column", height: "100dvh", background: "var(--surface-canvas)", color: "var(--text-primary)" }}>
    <header style={{ padding: "18px 24px", borderBottom: "1px solid var(--border-subtle)" }}>Fusion · Proje sohbeti</header>
    <Conversation mesajlar={messages} running={running} />
  </main>,
);
