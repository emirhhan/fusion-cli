import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { ConnectedOnboarding } from "../src/onboarding/ConnectedOnboarding";
import type { ProtocolClient } from "../src/protocol/client";
import { applyTheme } from "../src/theme/theme";
import "../src/theme/tokens.css";
const params = new URLSearchParams(location.search);
applyTheme(params.get("theme") === "dark" ? "dark" : "light");
localStorage.setItem("fusion.onboarding.progress.v1", JSON.stringify({ version: 1, step: params.get("step") ?? "providers", selectedProjectId: null }));
let saved = true;
const rows = () => [{ id: "openai", ad: "OpenAI", bagli: saved, eylem: "anahtar", tur: "anahtar" }, ...Array.from({ length: 30 }, (_, index) => ({ id: `fixture-${index}`, ad: `Sağlayıcı ${index + 1}`, bagli: false, eylem: "anahtar", tur: "anahtar" }))];
const client = { request: async (name: string) => {
  if (name === "kontrol.anahtar_kaydet") { saved = true; return { ok: true }; }
  if (name === "saglayici.katalog") return { ok: true, saglayicilar: rows() };
  if (name === "kontrol.durum") return { ok: true, model: {}, saglayicilar: rows().map(row => ({ id: row.id, ad: row.ad, kurulu: row.bagli })) };
  return { ok: true, kaynaklar: [] };
} } as unknown as ProtocolClient;
function Fixture() {
  const [finished, setFinished] = useState(false);
  return finished ? <p role="status">Test kurulumu tamamlandı</p> : <ConnectedOnboarding client={client} projects={[]} onFinish={() => setFinished(true)} />;
}
createRoot(document.getElementById("root")!).render(<Fixture />);
