import { useState } from "react";
import { Composer } from "../src/screens/Composer";
import { Conversation, type Mesaj } from "../src/screens/Conversation";

export function ActivityPanelFixture() {
  const initial = Number(new URLSearchParams(location.search).get("count") ?? "14");
  const empty = new URLSearchParams(location.search).get("empty") === "1";
  const [count, setCount] = useState(initial);
  const [session, setSession] = useState("first");
  const messages: Mesaj[] = [
    { id: "earlier-user", rol: "kullanici", metin: "Önceki görev" },
    { id: "earlier-answer", rol: "asistan", metin: Array.from({ length: 20 }, (_, i) => `Önceki açıklama ${i + 1}.`).join("\n\n") },
    { id: "user", rol: "kullanici", metin: "Dosyaları incele ve sonucu doğrula" },
    ...Array.from({ length: count }, (_, i): Mesaj => ({ id: `event-${i}`, rol: "olay", metin: "", adimlar: [{
      metin: `İşlem ${i + 1}`, arac: "run_shell", durum: "ok", ...(!empty ? { komut: `python kontrol_${i + 1}.py`,
      cikti: Array.from({ length: 60 }, (_, n) => `Kontrol ${i + 1} · çıktı satırı ${n + 1}`).join("\n"),
      ...(i === 1 ? { diff: "--- a/app.ts\n+++ b/app.ts\n-eski\n+yeni" } : {}), } : {}),
    }] })),
    { id: "narration", rol: "asistan", metin: "Kontrolleri gözden geçiriyorum; açıklamalar ana sohbette kalır.", ara: true },
    { id: "answer", rol: "asistan", metin: new URLSearchParams(location.search).get("tail") === "0" ? "Sonuç hazır." : Array.from({ length: 25 }, (_, i) => `Sonuç açıklaması ${i + 1}.`).join("\n\n") },
  ];
  return <main style={{ height: "100vh", display: "flex", flexDirection: "column", background: "var(--surface-canvas)" }}>
    <div style={{ display: "flex", gap: 12, padding: 12 }}>
      <button onClick={() => setCount(n => n + 1)}>İşlem ekle</button>
      <button onClick={() => window.setTimeout(() => setCount(n => n + 1), 200)}>Arka planda işlem ekle</button>
      <button onClick={() => setSession(n => n === "first" ? "second" : "first")}>Sohbet değiştir</button>
    </div>
    <Conversation key={session} running mesajlar={messages} />
    {new URLSearchParams(location.search).get("composer") === "1" && <Composer onSend={() => undefined} />}
  </main>;
}
