import React from "react";
import { createRoot } from "react-dom/client";
import { VoiceMode } from "../src/voice/VoiceMode";
import "../src/theme/tokens.css";
const params = new URLSearchParams(location.search);
document.documentElement.dataset.theme = params.get("theme") ?? "dark";
createRoot(document.getElementById("root")!).render(<VoiceMode onDrag={async () => { document.body.dataset.drags = String(Number(document.body.dataset.drags ?? 0) + 1); }} onListen={() => { document.body.dataset.listens = String(Number(document.body.dataset.listens ?? 0) + 1); }} listening={params.get("error") !== "1"} state={params.get("error") === "1" ? "error" : "listening"} transcript="macOS Dikte kapalı. Sistem Ayarları → Klavye → Dikte’yi açıp karaktere yeniden tıkla." wide={params.get("wide") === "1"} onClose={() => {}} onMinimize={() => {}} onWideChange={() => {}} onPrefsChange={() => {}} onTopChange={() => {}} />);
