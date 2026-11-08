import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { Composer } from "../src/screens/Composer";
import "../src/theme/tokens.css";
import "../src/brand/fonts.css";
document.documentElement.dataset.theme = "dark";
function Preview() {
  const [dictating, setDictating] = useState(false);
  const [running, setRunning] = useState(false);
  const [persona, setPersona] = useState<string | null>(null);
  return <main style={{ containerType: "inline-size", containerName: "conversation-workspace", display: "grid", alignContent: "end", minHeight: "100dvh", background: "var(--surface-canvas)" }}>
    <div style={{ position: "fixed", top: 8, left: 8, font: "12px system-ui", color: "#9de4fa" }}>ARAYÜZ TESTİ · MODEL/MİKROFON BAĞLI DEĞİL <button onClick={() => setRunning((v) => !v)}>Çalışma durumunu değiştir</button></div>
    <Composer onSend={() => undefined} onApprovalChange={() => {}} onWorkspaceModeChange={() => {}} workspaceMode="kod"
      activeModel="nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b" onModelSelect={() => {}}
      persona={persona} onPersonaChange={setPersona} personaOptions={[{ ad: "plan" }]}
      onDictation={() => setDictating((v) => !v)} dictating={dictating} onVoice={() => {}} running={running} onStop={() => setRunning(false)} />
  </main>;
}
createRoot(document.getElementById("root")!).render(<Preview />);
